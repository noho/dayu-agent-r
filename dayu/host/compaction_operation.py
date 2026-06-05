"""Host 内部 context compaction operation helper。

本模块只执行事务外 compaction proposal attempt 循环、质量校验与 proactive
预算硬阈值校验。reactive path 不把估算值当作是否可重新 dispatch 的真源；
EventLog 写入、artifact 写入、memory projection 与 durable state recheck 仍由
调用方所在的 Host governance 路径负责。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
from dayu.host.compact_material import conversation_compact_input_vnext_from_material_pack
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    CompactionRequest,
    ContextCompactor,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
)
from dayu.host.context_budget import DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS, estimate_budget_text_tokens
from dayu.host.context_governance import check_conversation_compact_output_vnext
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.payload import PayloadStore
from dayu.host.durable.schema import (
    COMPACTOR_INPUT_PROJECTION_DESCRIPTOR_KIND,
    RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND,
    RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.runtime.diagnostic_text import (
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

_DIAGNOSTIC_SUFFIX_UNKNOWN = "unknown"
_DIAGNOSTIC_SUFFIX_CANCELLED = "cancelled"
_DIAGNOSTIC_SUFFIX_HARD_THRESHOLD = "hard_threshold"
_MAX_SAFE_EXCEPTION_MESSAGE_CHARS = 240
_TRUNCATED_SUFFIX = "..."
_REDACTED_SECRET = "<redacted>"
_ERROR_CODE_PATTERN = re.compile(r"\berror_code=([A-Za-z0-9_-]+)")
_LOGGER = logging.getLogger(__name__)
_POST_COMPACT_BASE_MESSAGE_COUNT = 2
_EVENT_ID_RUNNER_CALL_INPUT_ASSEMBLED_PREFIX = "event-runner-call-input-assembled"
_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_RUNNER_CALL_KIND_COMPACTOR_PROPOSAL = "compactor_proposal"
_RUNNER_CALL_TRIGGER_COMPACTION_INITIAL = "context_compaction_initial_proposal"
_RUNNER_CALL_TRIGGER_COMPACTION_REPAIR = "context_compaction_repair_attempt"
_RUNNER_CALL_TRIGGER_COMPACTION_RETRY = "context_compaction_retry_attempt"
_RUNNER_CALL_VALIDATION_COMPLETE = "complete"
_COMPACTOR_INPUT_PROJECTION_MEDIA_TYPE = (
    "application/vnd.dayu.compactor-input-projection+json"
)
_COMPACTOR_PROJECTOR_SCHEMA_VERSION = "compactor_projector.v1"
_COMPACTOR_PROJECTOR_PURPOSE = "compactor_proposal_input"
_COMPACTOR_SYSTEM_PROJECTOR_ID = "compactor_system_prompt"
_COMPACTOR_USER_PROJECTOR_ID = "compactor_user_prompt"
_COMPACTOR_INPUT_PROJECTION_PAYLOAD_PREFIX = "compactor-input-projection"
_RUNNER_CALL_MANIFEST_PAYLOAD_PREFIX = "runner-call-manifest"
_GOVERNANCE_ACTOR = "host.context_governance"


@dataclass(frozen=True, slots=True)
class CompactorProposalRunInput:
    """compactor proposal 单次真实 runner call 输入。

    :param compact_input: 已冻结的 vNext compactor 输入结构。
    :param agent_request: 将交给 Engine public runner 的真实请求。
    :param compaction_request_digest: compaction request digest。
    :param compactor_engine_run_id: compactor Engine run id。
    :param message_count: 真实 runner messages 数量。
    :param role_sequence_digest: 真实 runner messages role 序列 digest。
    :param system_prompt_asset_digest: system prompt asset digest。
    :param user_prompt_template_digest: user prompt template digest。
    :param user_prompt_digest: 已渲染 user prompt digest。
    :param compactor_input_projection: compactor input projection artifact body。
    :param compactor_input_projection_digest: projection body digest。
    """

    compact_input: ConversationCompactInputVNext
    agent_request: AgentRunRequest
    compaction_request_digest: str
    compactor_engine_run_id: str
    message_count: int
    role_sequence_digest: str
    system_prompt_asset_digest: str
    user_prompt_template_digest: str
    user_prompt_digest: str
    compactor_input_projection: Mapping[str, JsonValue]
    compactor_input_projection_digest: str


@dataclass(frozen=True, slots=True)
class CompactorProposalManifestReference:
    """已持久化 compactor proposal manifest 引用。

    :param manifest_event_id: ``RUNNER_CALL_INPUT_ASSEMBLED`` event id。
    :param manifest_payload_ref: runner-call manifest payload descriptor ref。
    :param manifest_digest: runner-call manifest body digest。
    :param compactor_input_projection_ref: compactor input projection descriptor ref。
    :param compactor_input_projection_digest: compactor input projection digest。
    """

    manifest_event_id: str
    manifest_payload_ref: str
    manifest_digest: str
    compactor_input_projection_ref: str
    compactor_input_projection_digest: str


@runtime_checkable
class CompactorProposalPreparedCompactor(Protocol):
    """支持同源 proposal input 观测的 compactor 能力协议。"""

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
    ) -> CompactorProposalRunInput:
        """构造但不执行 compactor proposal runner call 输入。

        :param request: Host compaction request。
        :param cancellation_token: Host 注入 compactor 的真实取消 token。
        :param compaction_operation_id: Host compaction operation id；未知时为
            ``None``。
        :param compaction_attempt_number: operation 内 proposal attempt 序号。
        :returns: 真实 Engine runner call 输入与轻量观测。
        """

        ...

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> ConversationCompactOutputVNext:
        """执行已准备的 compactor proposal runner call。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: vNext compact output candidate。
        """

        ...


class CompactorProposalManifestRecorder(Protocol):
    """Host-owned compactor proposal manifest 记录器协议。"""

    def record_compactor_proposal_manifest(
        self,
        *,
        request: CompactionRequest,
        prepared_input: CompactorProposalRunInput,
        compaction_operation_id: str,
        compaction_attempt_number: int,
    ) -> CompactorProposalManifestReference:
        """在 proposal runner call 前持久化 input assembly manifest。

        :param request: Host compaction request。
        :param prepared_input: 同源真实 runner call 输入。
        :param compaction_operation_id: Host compaction operation id。
        :param compaction_attempt_number: operation 内 proposal attempt 序号。
        :returns: 已持久化 manifest 引用。
        """

        ...


class DurableCompactorProposalManifestRecorder(CompactorProposalManifestRecorder):
    """把 compactor proposal input assembly manifest 写入 Host durable store。

    :param transaction_runner: Host durable transaction runner。
    :param event_log_store: EventLog store。
    :param artifact_root: compact artifact root，也承载 compactor projection。
    :param create_artifact_root: artifact root 缺失时是否创建。
    :param event_source: 写入 EventLog 的 Host source。
    """

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore,
        artifact_root: Path,
        create_artifact_root: bool,
        event_source: str,
    ) -> None:
        """初始化 durable recorder。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog store。
        :param artifact_root: artifact root。
        :param create_artifact_root: artifact root 缺失时是否创建。
        :param event_source: 写入 EventLog 的 Host source。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = event_log_store
        self._artifact_store = LocalArtifactStore(
            artifact_root,
            create_artifact_root=create_artifact_root,
        )
        self._payload_store = PayloadStore()
        self._event_source = event_source

    def record_compactor_proposal_manifest(
        self,
        *,
        request: CompactionRequest,
        prepared_input: CompactorProposalRunInput,
        compaction_operation_id: str,
        compaction_attempt_number: int,
    ) -> CompactorProposalManifestReference:
        """在 proposal runner call 前写入 durable manifest。

        :param request: Host compaction request。
        :param prepared_input: 同源真实 runner call 输入。
        :param compaction_operation_id: Host compaction operation id。
        :param compaction_attempt_number: operation 内 proposal attempt 序号。
        :returns: 已持久化 manifest 引用。
        """

        event_id = _new_event_id(_EVENT_ID_RUNNER_CALL_INPUT_ASSEMBLED_PREFIX)

        def _operation(transaction: HostTransaction) -> CompactorProposalManifestReference:
            projection_ref = _compactor_input_projection_ref(event_id)
            projection_artifact_ref = self._artifact_store.write_artifact_bytes(
                canonical_json_dumps(
                    prepared_input.compactor_input_projection
                ).encode("utf-8"),
                expected_digest=prepared_input.compactor_input_projection_digest,
            )
            projection_descriptor = self._payload_store.write_payload_descriptor_for_artifact(
                transaction,
                projection_ref,
                projection_artifact_ref,
                _COMPACTOR_INPUT_PROJECTION_MEDIA_TYPE,
                {
                    "descriptor_kind": COMPACTOR_INPUT_PROJECTION_DESCRIPTOR_KIND,
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                    "compaction_operation_id": compaction_operation_id,
                    "compaction_attempt_number": compaction_attempt_number,
                    "compaction_request_digest": prepared_input.compaction_request_digest,
                },
            )
            manifest = _compactor_runner_call_manifest_body(
                request=request,
                prepared_input=prepared_input,
                event_id=event_id,
                compaction_operation_id=compaction_operation_id,
                compaction_attempt_number=compaction_attempt_number,
                compactor_input_projection_ref=projection_descriptor.payload_ref,
            )
            manifest_digest = sha256_digest_json(manifest)
            manifest_artifact_ref = self._artifact_store.write_artifact_bytes(
                canonical_json_dumps(manifest).encode("utf-8"),
                expected_digest=manifest_digest,
            )
            manifest_payload_ref = _runner_call_manifest_payload_ref(event_id)
            manifest_descriptor = self._payload_store.write_payload_descriptor_for_artifact(
                transaction,
                manifest_payload_ref,
                manifest_artifact_ref,
                RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
                {
                    "descriptor_kind": RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND,
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                    "schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
                    "compaction_operation_id": compaction_operation_id,
                    "compaction_attempt_number": compaction_attempt_number,
                },
            )
            self._event_log_store.append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=event_id,
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    attempt_id=request.attempt_id,
                    execution_id=request.execution_id,
                    event_type=_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    occurred_at=datetime.now(UTC),
                    actor=_GOVERNANCE_ACTOR,
                    source=self._event_source,
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason={"runner_call_kind": _RUNNER_CALL_KIND_COMPACTOR_PROPOSAL},
                    payload_json=_compactor_runner_call_hot_payload(
                        manifest=manifest,
                        manifest_payload_ref=manifest_descriptor.payload_ref,
                        manifest_digest=manifest_digest,
                    ),
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            return CompactorProposalManifestReference(
                manifest_event_id=event_id,
                manifest_payload_ref=manifest_descriptor.payload_ref,
                manifest_digest=manifest_digest,
                compactor_input_projection_ref=projection_descriptor.payload_ref,
                compactor_input_projection_digest=(
                    prepared_input.compactor_input_projection_digest
                ),
            )

        return self._transaction_runner.run_write(_operation)


class CompactionFailureCategory(StrEnum):
    """compaction attempt 拒绝原因分类。"""

    PROPOSAL_FAILED = "proposal_failed"
    QUALITY_CHECK_REJECTED = "quality_check_rejected"
    HARD_THRESHOLD_AFTER_COMPACT = "hard_threshold_after_compact"
    MAX_ATTEMPTS_EXHAUSTED = "max_compaction_attempts_exhausted"
    CANCELLATION_REQUESTED = "cancellation_requested"


class CompactionNextPolicyDecision(StrEnum):
    """compaction attempt 拒绝后的下一步策略决策。"""

    RETRY_SEMANTIC_REPAIR = "retry_semantic_repair"
    FAIL_COMPACTION = "fail_compaction"


_FAILURE_PROPOSAL_FAILED = CompactionFailureCategory.PROPOSAL_FAILED
_FAILURE_QUALITY_CHECK_REJECTED = CompactionFailureCategory.QUALITY_CHECK_REJECTED
_FAILURE_HARD_THRESHOLD_AFTER_COMPACT = (
    CompactionFailureCategory.HARD_THRESHOLD_AFTER_COMPACT
)
_FAILURE_MAX_ATTEMPTS_EXHAUSTED = CompactionFailureCategory.MAX_ATTEMPTS_EXHAUSTED
_FAILURE_CANCELLATION_REQUESTED = CompactionFailureCategory.CANCELLATION_REQUESTED
_NEXT_DECISION_RETRY_REPAIR = CompactionNextPolicyDecision.RETRY_SEMANTIC_REPAIR
_NEXT_DECISION_FAIL_COMPACTION = CompactionNextPolicyDecision.FAIL_COMPACTION


@dataclass(frozen=True, slots=True)
class CompactionAttemptRejected:
    """compaction semantic attempt reject 摘要。

    :param attempt_number: operation 内 proposal attempt 序号。
    :param failure_category: 失败类别。
    :param repairable: 是否可继续 repair attempt。
    :param runner_attempt_summary_refs: runner attempt 摘要 ref。
    :param diagnostic_refs: quality / parse / budget 诊断 ref。
    :param next_policy_decision: 下一步 policy decision。
    :param budget_after_attempted_compact: attempt 后预算；未知时为 ``None``。
    :param proposal_manifest_ref: 对应该 proposal attempt 的 manifest ref。
    :param proposal_manifest_digest: 对应该 proposal attempt 的 manifest digest。
    """

    attempt_number: int
    failure_category: CompactionFailureCategory
    repairable: bool
    runner_attempt_summary_refs: tuple[str, ...]
    diagnostic_refs: tuple[str, ...]
    next_policy_decision: CompactionNextPolicyDecision
    budget_after_attempted_compact: int | None
    proposal_manifest_ref: str | None
    proposal_manifest_digest: str | None


@dataclass(frozen=True, slots=True)
class CompactionOperationResult:
    """事务外 compaction operation 结果。

    :param accepted_candidate: 被 Host 接受的 candidate；失败时为 ``None``。
    :param quality_result: accepted candidate 对应 quality result。
    :param rejected_attempts: semantic attempt reject 诊断列表。
    :param failure_reason: 最终失败原因；成功时为 ``None``。
    :param budget_after_attempted_compact: 最后一次 attempt 后预算；未知时为
        ``None``。
    :param accepted_proposal_manifest_ref: accepted proposal manifest ref。
    :param accepted_proposal_manifest_digest: accepted proposal manifest digest。
    """

    accepted_candidate: ConversationCompactOutputVNext | None
    quality_result: CompactQualityCheckResultVNext | None
    rejected_attempts: tuple[CompactionAttemptRejected, ...]
    failure_reason: str | None
    budget_after_attempted_compact: int | None
    accepted_proposal_manifest_ref: str | None = None
    accepted_proposal_manifest_digest: str | None = None


@dataclass(frozen=True, slots=True)
class _CompactorProposalAttempt:
    """单次 proposal attempt 执行结果。

    :param compact_input: quality check 使用的同源 compactor input。
    :param candidate: compactor 返回的 candidate。
    :param proposal_manifest_reference: 调用前写入的 manifest ref；未记录时为
        ``None``。
    """

    compact_input: ConversationCompactInputVNext
    candidate: ConversationCompactOutputVNext
    proposal_manifest_reference: CompactorProposalManifestReference | None


@dataclass(frozen=True, slots=True)
class _CompactorProposalExecutionError(Exception):
    """proposal 执行失败并携带已写 manifest ref。

    :param original_exception: 原始 proposal 异常。
    :param proposal_manifest_reference: 已写 manifest ref。
    """

    original_exception: Exception
    proposal_manifest_reference: CompactorProposalManifestReference | None


async def run_compaction_operation(
    *,
    request: CompactionRequest,
    compactor: ContextCompactor,
    max_attempts: int,
    cancellation_token: CancellationToken,
    pass_queue: tuple[CompactionRequest, ...] = (),
    compaction_operation_id: str | None = None,
    proposal_manifest_recorder: CompactorProposalManifestRecorder | None = None,
) -> CompactionOperationResult:
    """在事务外执行 Host semantic compaction operation。

    :param request: Host compaction request。
    :param compactor: Host internal compactor seam。
    :param max_attempts: proposal attempt 上限。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :param pass_queue: 同一 operation 内的 pass request 队列；为空时使用
        ``request`` 作为单 pass。
    :param compaction_operation_id: Host compaction operation id；生产路径必须传入。
    :param proposal_manifest_recorder: compactor proposal manifest 记录器。
    :returns: compaction operation 结果。
    """

    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    requests = _operation_pass_requests(request=request, pass_queue=pass_queue)
    rejected: list[CompactionAttemptRejected] = []
    last_budget: int | None = None
    accepted_candidate: ConversationCompactOutputVNext | None = None
    accepted_quality: CompactQualityCheckResultVNext | None = None
    accepted_manifest_reference: CompactorProposalManifestReference | None = None
    attempt_number = 1
    for pass_request in requests:
        pass_accepted = False
        while attempt_number <= max_attempts and not pass_accepted:
            proposal_manifest_reference: CompactorProposalManifestReference | None = None
            if cancellation_token.is_cancelled():
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_CANCELLATION_REQUESTED,
                    repairable=False,
                    next_policy_decision=_NEXT_DECISION_FAIL_COMPACTION,
                    budget_after_attempted_compact=last_budget,
                    diagnostic_suffix=_cancellation_suffix(cancellation_token),
                    proposal_manifest_reference=proposal_manifest_reference,
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=None,
                )
                return CompactionOperationResult(
                    accepted_candidate=None,
                    quality_result=None,
                    rejected_attempts=tuple(rejected),
                    failure_reason=_FAILURE_CANCELLATION_REQUESTED.value,
                    budget_after_attempted_compact=last_budget,
                    accepted_proposal_manifest_ref=None,
                    accepted_proposal_manifest_digest=None,
                )
            repairable = attempt_number < max_attempts
            next_decision = _NEXT_DECISION_RETRY_REPAIR if repairable else _NEXT_DECISION_FAIL_COMPACTION
            try:
                proposal = await _prepare_compactor_proposal(
                    compactor,
                    pass_request,
                    cancellation_token,
                    compaction_operation_id=compaction_operation_id,
                    compaction_attempt_number=attempt_number,
                    proposal_manifest_recorder=proposal_manifest_recorder,
                )
                compact_input = proposal.compact_input
                proposal_manifest_reference = proposal.proposal_manifest_reference
                candidate = proposal.candidate
            except _CompactorProposalExecutionError as exc:
                proposal_manifest_reference = exc.proposal_manifest_reference
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=None,
                    diagnostic_suffix=_exception_diagnostic_suffix(
                        exc.original_exception
                    ),
                    proposal_manifest_reference=proposal_manifest_reference,
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=exc.original_exception,
                )
                if not repairable:
                    return CompactionOperationResult(
                        accepted_candidate=None,
                        quality_result=None,
                        rejected_attempts=tuple(rejected),
                        failure_reason=_FAILURE_PROPOSAL_FAILED.value,
                        budget_after_attempted_compact=None,
                        accepted_proposal_manifest_ref=None,
                        accepted_proposal_manifest_digest=None,
                    )
                attempt_number += 1
                continue
            except Exception as exc:
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=None,
                    diagnostic_suffix=_exception_diagnostic_suffix(exc),
                    proposal_manifest_reference=proposal_manifest_reference,
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=exc,
                )
                if not repairable:
                    return CompactionOperationResult(
                        accepted_candidate=None,
                        quality_result=None,
                        rejected_attempts=tuple(rejected),
                        failure_reason=_FAILURE_PROPOSAL_FAILED.value,
                        budget_after_attempted_compact=None,
                        accepted_proposal_manifest_ref=None,
                        accepted_proposal_manifest_digest=None,
                    )
                attempt_number += 1
                continue
            quality = check_conversation_compact_output_vnext(compact_input, candidate)
            last_budget = _budget_after_compact_candidate(pass_request, compact_input, candidate)
            if not quality.accepted:
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_QUALITY_CHECK_REJECTED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=last_budget,
                    diagnostic_suffix=_quality_suffix_vnext(quality),
                    proposal_manifest_reference=proposal_manifest_reference,
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=None,
                )
                if not repairable:
                    return CompactionOperationResult(
                        accepted_candidate=None,
                        quality_result=None,
                        rejected_attempts=tuple(rejected),
                        failure_reason=_FAILURE_QUALITY_CHECK_REJECTED.value,
                        budget_after_attempted_compact=last_budget,
                        accepted_proposal_manifest_ref=None,
                        accepted_proposal_manifest_digest=None,
                    )
                attempt_number += 1
                continue
            if _requires_budget_acceptance(pass_request) and (
                last_budget >= pass_request.budget_before_compact.hard_threshold_tokens
            ):
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=last_budget,
                    diagnostic_suffix=_DIAGNOSTIC_SUFFIX_HARD_THRESHOLD,
                    proposal_manifest_reference=proposal_manifest_reference,
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=None,
                )
                if not repairable:
                    return CompactionOperationResult(
                        accepted_candidate=None,
                        quality_result=None,
                        rejected_attempts=tuple(rejected),
                        failure_reason=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT.value,
                        budget_after_attempted_compact=last_budget,
                        accepted_proposal_manifest_ref=None,
                        accepted_proposal_manifest_digest=None,
                    )
                attempt_number += 1
                continue
            pass_accepted = True
            accepted_candidate = candidate
            accepted_quality = quality
            accepted_manifest_reference = proposal_manifest_reference
            attempt_number += 1
        if not pass_accepted:
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=tuple(rejected),
                failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED.value,
                budget_after_attempted_compact=last_budget,
                accepted_proposal_manifest_ref=None,
                accepted_proposal_manifest_digest=None,
            )
    if accepted_candidate is None or accepted_quality is None:
        return CompactionOperationResult(
            accepted_candidate=None,
            quality_result=None,
            rejected_attempts=tuple(rejected),
            failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED.value,
            budget_after_attempted_compact=last_budget,
            accepted_proposal_manifest_ref=None,
            accepted_proposal_manifest_digest=None,
        )
    return CompactionOperationResult(
        accepted_candidate=accepted_candidate,
        quality_result=accepted_quality,
        rejected_attempts=tuple(rejected),
        failure_reason=None,
        budget_after_attempted_compact=last_budget,
        accepted_proposal_manifest_ref=(
            None
            if accepted_manifest_reference is None
            else accepted_manifest_reference.manifest_payload_ref
        ),
        accepted_proposal_manifest_digest=(
            None
            if accepted_manifest_reference is None
            else accepted_manifest_reference.manifest_digest
        ),
    )


def _operation_pass_requests(
    *, request: CompactionRequest, pass_queue: tuple[CompactionRequest, ...]
) -> tuple[CompactionRequest, ...]:
    """返回 operation 实际 pass request 队列。

    :param request: operation root request。
    :param pass_queue: 调用方提供的 pass request 队列。
    :returns: 非空 pass request tuple。
    :raises TypeError: 队列元素类型非法时抛出。
    :raises ValueError: pass queue 与 root operation identity 不一致时抛出。
    """

    if len(pass_queue) == 0:
        return (request,)
    for pass_request in pass_queue:
        if not isinstance(pass_request, CompactionRequest):
            raise TypeError("pass_queue items must be CompactionRequest")
        if (
            pass_request.trigger_source is not request.trigger_source
            or pass_request.session_id != request.session_id
            or pass_request.run_id != request.run_id
            or pass_request.attempt_id != request.attempt_id
            or pass_request.execution_id != request.execution_id
        ):
            raise ValueError("pass_queue request identity must match root request")
    return pass_queue


def _requires_budget_acceptance(request: CompactionRequest) -> bool:
    """判断本次 operation 是否需要 compact 后预算估算闸门。

    proactive path 在 dispatch 前使用估算值决定是否创建 Attempt；reactive path
    来自真实 provider overflow，compact 后是否足够应交给后续真实 dispatch /
    Engine event 闭环判断，避免不准估算阻断第二次 reactive compact。

    :param request: Host compaction request。
    :returns: 需要估算闸门时返回 ``True``。
    """

    return request.trigger_source is ContextCompactionTriggerSource.PROACTIVE


async def _prepare_compactor_proposal(
    compactor: ContextCompactor,
    request: CompactionRequest,
    cancellation_token: CancellationToken,
    *,
    compaction_operation_id: str | None,
    compaction_attempt_number: int,
    proposal_manifest_recorder: CompactorProposalManifestRecorder | None,
) -> _CompactorProposalAttempt:
    """准备、记录并执行一次 compactor proposal。

    :param compactor: Host internal compactor seam。
    :param request: Host compaction request。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :param compaction_operation_id: Host compaction operation id。
    :param compaction_attempt_number: operation 内 proposal attempt 序号。
    :param proposal_manifest_recorder: proposal manifest 记录器。
    :returns: proposal attempt 结果。
    :raises TypeError: compactor 不支持 vNext capability 时抛出。
    """

    if isinstance(compactor, CompactorProposalPreparedCompactor):
        prepared_input = compactor.prepare_compactor_proposal_run_input(
            request,
            cancellation_token,
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
        )
        manifest_reference = _record_compactor_proposal_manifest(
            recorder=proposal_manifest_recorder,
            request=request,
            prepared_input=prepared_input,
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
        )
        try:
            candidate = await compactor.run_prepared_compactor_proposal(
                prepared_input
            )
        except Exception as exc:
            raise _CompactorProposalExecutionError(
                original_exception=exc,
                proposal_manifest_reference=manifest_reference,
            ) from exc
        return _CompactorProposalAttempt(
            compact_input=prepared_input.compact_input,
            candidate=candidate,
            proposal_manifest_reference=manifest_reference,
        )
    compact_input = conversation_compact_input_vnext_from_material_pack(
        request.material_pack
    )
    return _CompactorProposalAttempt(
        compact_input=compact_input,
        candidate=await compactor.compact(request, cancellation_token),
        proposal_manifest_reference=None,
    )


def _record_compactor_proposal_manifest(
    *,
    recorder: CompactorProposalManifestRecorder | None,
    request: CompactionRequest,
    prepared_input: CompactorProposalRunInput,
    compaction_operation_id: str | None,
    compaction_attempt_number: int,
) -> CompactorProposalManifestReference | None:
    """在 proposal runner call 前记录 manifest。

    :param recorder: manifest recorder；缺失时不记录。
    :param request: Host compaction request。
    :param prepared_input: 已准备的同源 runner call 输入。
    :param compaction_operation_id: Host compaction operation id。
    :param compaction_attempt_number: operation 内 proposal attempt 序号。
    :returns: manifest reference；未配置 recorder 时为 ``None``。
    :raises ValueError: recorder 存在但缺少 operation id 时抛出。
    """

    if recorder is None:
        return None
    if compaction_operation_id is None:
        raise ValueError("compaction_operation_id is required for proposal manifest")
    return recorder.record_compactor_proposal_manifest(
        request=request,
        prepared_input=prepared_input,
        compaction_operation_id=compaction_operation_id,
        compaction_attempt_number=compaction_attempt_number,
    )


def _new_event_id(prefix: str) -> str:
    """生成事件 id。

    :param prefix: id 前缀。
    :returns: 新事件 id。
    """

    return f"{prefix}-{uuid4().hex}"


def _compactor_runner_call_manifest_body(
    *,
    request: CompactionRequest,
    prepared_input: CompactorProposalRunInput,
    event_id: str,
    compaction_operation_id: str,
    compaction_attempt_number: int,
    compactor_input_projection_ref: str,
) -> Mapping[str, JsonValue]:
    """构造 compactor proposal runner-call manifest body。

    :param request: Host compaction request。
    :param prepared_input: 同源真实 runner call 输入。
    :param event_id: ``RUNNER_CALL_INPUT_ASSEMBLED`` event id。
    :param compaction_operation_id: Host compaction operation id。
    :param compaction_attempt_number: operation 内 proposal attempt 序号。
    :param compactor_input_projection_ref: compactor input projection descriptor ref。
    :returns: manifest canonical JSON object。
    """

    message_entries = _compactor_message_entries(
        prepared_input=prepared_input,
        compactor_input_projection_ref=compactor_input_projection_ref,
    )
    projector_metadata = _compactor_projector_metadata(
        request=request,
        prepared_input=prepared_input,
        compactor_input_projection_ref=compactor_input_projection_ref,
    )
    source_cursor_refs = _compactor_source_cursor_refs(request)
    input_projection_digest = sha256_digest_json(
        {
            "message_entries": list(message_entries),
            "projector_metadata": list(projector_metadata),
            "source_cursor_refs": list(source_cursor_refs),
            "compactor_input_projection_ref": compactor_input_projection_ref,
            "compactor_input_projection_digest": (
                prepared_input.compactor_input_projection_digest
            ),
        }
    )
    return {
        "schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "manifest_id": f"runner-call-manifest:{event_id}",
        "session_id": request.session_id,
        "host_run_id": request.run_id,
        "attempt_id": request.attempt_id,
        "execution_id": request.execution_id,
        "runner_call_index": compaction_attempt_number - 1,
        "runner_call_kind": _RUNNER_CALL_KIND_COMPACTOR_PROPOSAL,
        "runner_call_trigger_reason": _compactor_trigger_reason(
            compaction_attempt_number
        ),
        "iteration_id": None,
        "iteration_index": None,
        "message_count": prepared_input.message_count,
        "role_sequence_digest": prepared_input.role_sequence_digest,
        "runner_input_serializer_schema_version": (
            RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
        ),
        "input_projection_digest": input_projection_digest,
        "message_entries": list(message_entries),
        "source_cursor_refs": list(source_cursor_refs),
        "tool_schema_snapshot_refs": [],
        "memory_snapshot_cursor_ref": request.memory_snapshot_cursor,
        "compact_artifact_refs": [],
        "context_fallback_decision_ref": None,
        "projector_metadata": list(projector_metadata),
        "compactor_identity": {
            "parent_host_run_id": request.run_id,
            "parent_session_id": request.session_id,
            "compaction_operation_id": compaction_operation_id,
            "compactor_engine_run_id": prepared_input.compactor_engine_run_id,
            "compaction_attempt_number": compaction_attempt_number,
            "compaction_request_digest": prepared_input.compaction_request_digest,
            "compactor_input_projection_ref": compactor_input_projection_ref,
        },
        "diagnostic": None,
    }


def _compactor_runner_call_hot_payload(
    *,
    manifest: Mapping[str, JsonValue],
    manifest_payload_ref: str,
    manifest_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 compactor proposal ``RUNNER_CALL_INPUT_ASSEMBLED`` hot payload。

    :param manifest: runner-call manifest body。
    :param manifest_payload_ref: manifest payload descriptor ref。
    :param manifest_digest: manifest body digest。
    :returns: EventLog hot payload。
    """

    return {
        "session_id": _required_manifest_text(manifest, "session_id"),
        "host_run_id": _required_manifest_text(manifest, "host_run_id"),
        "attempt_id": _optional_manifest_text(manifest, "attempt_id"),
        "execution_id": _optional_manifest_text(manifest, "execution_id"),
        "runner_call_index": _required_manifest_int(
            manifest, "runner_call_index"
        ),
        "runner_call_kind": _required_manifest_text(manifest, "runner_call_kind"),
        "runner_call_trigger_reason": _required_manifest_text(
            manifest,
            "runner_call_trigger_reason",
        ),
        "iteration_id": None,
        "iteration_index": None,
        "manifest_payload_ref": manifest_payload_ref,
        "manifest_digest": manifest_digest,
        "manifest_schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "validation_status": _RUNNER_CALL_VALIDATION_COMPLETE,
        "message_count": _required_manifest_int(manifest, "message_count"),
        "role_sequence_digest": _required_manifest_text(
            manifest,
            "role_sequence_digest",
        ),
        "input_projection_digest": _required_manifest_text(
            manifest,
            "input_projection_digest",
        ),
        "projector_metadata_summary": _projector_metadata_summary(manifest),
        "diagnostic": None,
    }


def _compactor_message_entries(
    *,
    prepared_input: CompactorProposalRunInput,
    compactor_input_projection_ref: str,
) -> tuple[Mapping[str, JsonValue], ...]:
    """构造 compactor manifest message summaries。

    :param prepared_input: 同源真实 runner call 输入。
    :param compactor_input_projection_ref: compactor input projection ref。
    :returns: message summary tuple。
    """

    entries: list[Mapping[str, JsonValue]] = []
    for index, message in enumerate(prepared_input.agent_request.messages):
        message_content = "" if message.content is None else message.content
        entries.append(
            {
                "index": index,
                "role": message.role.value,
                "content_digest": sha256_digest_json(
                    {"message_content": message_content}
                ),
                "content_size_bytes": len(message_content.encode("utf-8")),
                "source_refs": list(
                    _compactor_message_source_refs(
                        index=index,
                        prepared_input=prepared_input,
                        compactor_input_projection_ref=(
                            compactor_input_projection_ref
                        ),
                    )
                ),
                "projection_artifact_ref": (
                    None if index == 0 else compactor_input_projection_ref
                ),
                "projection_artifact_digest": (
                    None
                    if index == 0
                    else prepared_input.compactor_input_projection_digest
                ),
                "projector_metadata_id": _compactor_projector_metadata_id(index),
                "provider_tool_calls_digest": None,
                "reasoning_content_digest": None,
            }
        )
    return tuple(entries)


def _compactor_projector_metadata(
    *,
    request: CompactionRequest,
    prepared_input: CompactorProposalRunInput,
    compactor_input_projection_ref: str,
) -> tuple[Mapping[str, JsonValue], ...]:
    """构造 compactor projector metadata。

    :param request: Host compaction request。
    :param prepared_input: 同源真实 runner call 输入。
    :param compactor_input_projection_ref: compactor input projection ref。
    :returns: projector metadata tuple。
    """

    return (
        {
            "metadata_id": _compactor_projector_metadata_id(0),
            "projector_id": _COMPACTOR_SYSTEM_PROJECTOR_ID,
            "projector_schema_version": _COMPACTOR_PROJECTOR_SCHEMA_VERSION,
            "purpose": _COMPACTOR_PROJECTOR_PURPOSE,
            "source_contract_refs": [
                f"prompt-digest:{prepared_input.system_prompt_asset_digest}"
            ],
            "projector_digest": prepared_input.system_prompt_asset_digest,
        },
        {
            "metadata_id": _compactor_projector_metadata_id(1),
            "projector_id": _COMPACTOR_USER_PROJECTOR_ID,
            "projector_schema_version": _COMPACTOR_PROJECTOR_SCHEMA_VERSION,
            "purpose": _COMPACTOR_PROJECTOR_PURPOSE,
            "source_contract_refs": [
                compactor_input_projection_ref,
                *_compactor_source_cursor_refs(request),
            ],
            "projector_digest": prepared_input.user_prompt_digest,
        },
    )


def _compactor_message_source_refs(
    *,
    index: int,
    prepared_input: CompactorProposalRunInput,
    compactor_input_projection_ref: str,
) -> tuple[str, ...]:
    """返回 compactor message source refs。

    :param index: message index。
    :param prepared_input: 同源真实 runner call 输入。
    :param compactor_input_projection_ref: compactor input projection ref。
    :returns: source refs。
    """

    if index == 0:
        return (f"prompt-digest:{prepared_input.system_prompt_asset_digest}",)
    return (
        f"prompt-template-digest:{prepared_input.user_prompt_template_digest}",
        compactor_input_projection_ref,
    )


def _compactor_projector_metadata_id(index: int) -> str:
    """返回 compactor projector metadata id。

    :param index: message index。
    :returns: projector metadata id。
    """

    if index == 0:
        return "compactor-projector:system"
    return "compactor-projector:user"


def _compactor_source_cursor_refs(request: CompactionRequest) -> tuple[str, ...]:
    """返回 compactor manifest source cursor refs。

    :param request: Host compaction request。
    :returns: 去重后的 source refs。
    """

    return tuple(
        dict.fromkeys(
            (
                request.current_input_ref,
                *request.material_source_refs,
                *request.canonical_evidence_refs,
                *request.evidence_backed_fact_refs,
                *request.recent_raw_turn_refs,
                *request.older_raw_turn_refs,
                *request.existing_episode_summary_refs,
            )
        )
    )


def _projector_metadata_summary(
    manifest: Mapping[str, JsonValue]
) -> list[JsonValue]:
    """从 manifest projector metadata 构造 hot payload summary。

    :param manifest: runner-call manifest body。
    :returns: bounded projector metadata summary。
    """

    metadata = manifest.get("projector_metadata")
    if not isinstance(metadata, list):
        return []
    summary: list[JsonValue] = []
    for entry in metadata:
        if isinstance(entry, Mapping):
            summary.append(
                {
                    "metadata_id": entry.get("metadata_id"),
                    "projector_id": entry.get("projector_id"),
                    "purpose": entry.get("purpose"),
                    "projector_digest": entry.get("projector_digest"),
                }
            )
    return summary


def _compactor_trigger_reason(compaction_attempt_number: int) -> str:
    """返回 compactor proposal trigger reason。

    :param compaction_attempt_number: operation 内 proposal attempt 序号。
    :returns: runner call trigger reason。
    """

    if compaction_attempt_number <= 1:
        return _RUNNER_CALL_TRIGGER_COMPACTION_INITIAL
    return _RUNNER_CALL_TRIGGER_COMPACTION_RETRY


def _compactor_input_projection_ref(event_id: str) -> str:
    """派生 compactor input projection descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_COMPACTOR_INPUT_PROJECTION_PAYLOAD_PREFIX}:{event_id}"


def _runner_call_manifest_payload_ref(event_id: str) -> str:
    """派生 compactor runner-call manifest descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_RUNNER_CALL_MANIFEST_PAYLOAD_PREFIX}:{event_id}"


def _required_manifest_text(
    manifest: Mapping[str, JsonValue],
    field_name: str,
) -> str:
    """读取 manifest 必填文本字段。

    :param manifest: runner-call manifest body。
    :param field_name: 字段名。
    :returns: 文本字段。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    value = manifest.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")
    return value


def _optional_manifest_text(
    manifest: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取 manifest 可选文本字段。

    :param manifest: runner-call manifest body。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但类型非法时抛出。
    """

    value = manifest.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")
    return value


def _required_manifest_int(
    manifest: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取 manifest 必填整数。

    :param manifest: runner-call manifest body。
    :param field_name: 字段名。
    :returns: int 字段。
    :raises HostDurableError: 字段缺失、类型非法或为负数时抛出。
    """

    value = manifest.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"{field_name} must be non-negative int")
    return value


def _budget_after_compact_candidate(
    request: CompactionRequest,
    compact_input: ConversationCompactInputVNext,
    candidate: ConversationCompactOutputVNext,
) -> int:
    """估算 vNext compact 后预算。

    预算是 Host governance 诊断，不由 LLM candidate 输出。本估算只读取
    accepted candidate 的业务可读文本、当前输入和必须保留的边界 refs。

    :param request: operation root request。
    :param compact_input: 本次发送给 compactor 的 vNext input。
    :param candidate: vNext compact output。
    :returns: 非负 token 估算。
    """

    fragments = (
        *_candidate_text_fragments(candidate),
        compact_input.current_input_anchor.text,
    )
    token_count = sum(max(1, estimate_budget_text_tokens(fragment)) for fragment in fragments)
    return token_count + (
        DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS * _POST_COMPACT_BASE_MESSAGE_COUNT
    )


def _candidate_text_fragments(candidate: ConversationCompactOutputVNext) -> tuple[str, ...]:
    """收集 vNext candidate 中会被后续 projection 消费的文本片段。

    :param candidate: vNext compact output。
    :returns: 文本片段 tuple。
    """

    fragments: list[str] = []
    if candidate.session_summary is not None:
        fragments.append(candidate.session_summary.summary_text)
    for fact in candidate.evidence_backed_facts:
        fragments.append(fact.claim_text)
    for anchor in candidate.answer_anchors:
        fragments.append(anchor.anchor_title)
        fragments.extend(item.display_text for item in anchor.anchor_items)
    for intent in candidate.forward_intents:
        fragments.append(intent.text)
    for item in candidate.reference_continuity_items:
        fragments.append(item.text)
    for diagnostic in candidate.diagnostics:
        fragments.append(diagnostic.code)
        fragments.append(diagnostic.text)
    return tuple(fragments)


def _attempt_rejected(
    *,
    request: CompactionRequest,
    attempt_number: int,
    failure_category: CompactionFailureCategory,
    repairable: bool,
    next_policy_decision: CompactionNextPolicyDecision,
    budget_after_attempted_compact: int | None,
    diagnostic_suffix: str,
    proposal_manifest_reference: CompactorProposalManifestReference | None,
) -> CompactionAttemptRejected:
    """构造 attempt reject 摘要。

    :param request: Host compaction request。
    :param attempt_number: proposal attempt 序号。
    :param failure_category: 失败类别。
    :param repairable: 是否可继续 repair attempt。
    :param next_policy_decision: 下一步 policy decision。
    :param budget_after_attempted_compact: attempt 后预算。
    :param diagnostic_suffix: 诊断 ref 后缀。
    :param proposal_manifest_reference: proposal manifest ref。
    :returns: attempt reject 摘要。
    """

    operation_ref = request.digest()
    return CompactionAttemptRejected(
        attempt_number=attempt_number,
        failure_category=failure_category,
        repairable=repairable,
        runner_attempt_summary_refs=(f"runner-attempt:{request.run_id}:{attempt_number}",),
        diagnostic_refs=(
            f"diagnostic:{failure_category.value}:{operation_ref}:{diagnostic_suffix}",
        ),
        next_policy_decision=next_policy_decision,
        budget_after_attempted_compact=budget_after_attempted_compact,
        proposal_manifest_ref=(
            None
            if proposal_manifest_reference is None
            else proposal_manifest_reference.manifest_payload_ref
        ),
        proposal_manifest_digest=(
            None
            if proposal_manifest_reference is None
            else proposal_manifest_reference.manifest_digest
        ),
    )


def _quality_suffix_vnext(quality: CompactQualityCheckResultVNext) -> str:
    """构造 quality reject 诊断后缀。

    :param quality: quality check 结果。
    :returns: 中性诊断后缀。
    """

    if len(quality.rejection_reasons) == 0:
        return _DIAGNOSTIC_SUFFIX_UNKNOWN
    return "-".join(reason.value for reason in quality.rejection_reasons)


def _exception_diagnostic_suffix(exc: Exception) -> str:
    """构造 proposal exception 诊断后缀。

    :param exc: compactor proposal 抛出的异常。
    :returns: 包含异常类型与消息的诊断后缀。
    """

    message = _safe_exception_message(exc)
    if message == exc.__class__.__name__:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}:{message}"


def _cancellation_suffix(cancellation_token: CancellationToken) -> str:
    """构造取消拒绝诊断后缀。

    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :returns: 取消原因；token 未提供原因时返回中性取消后缀。
    :raises Exception: 不主动抛出异常。
    """

    reason = cancellation_token.cancel_reason()
    if reason is None or reason.strip() == "":
        return _DIAGNOSTIC_SUFFIX_CANCELLED
    return reason


def _log_rejected_attempt(
    *,
    request: CompactionRequest,
    rejected: CompactionAttemptRejected,
    exception: Exception | None,
) -> None:
    """记录 compaction attempt 拒绝摘要。

    :param request: Host compaction request。
    :param rejected: attempt reject 摘要。
    :param exception: proposal 异常；非异常类拒绝时为 ``None``。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    log_message = (
        "host.compaction_operation.attempt_rejected "
        "session_id=%s run_id=%s trigger_source=%s attempt_number=%s "
        "failure_category=%s repairable=%s error_code=%s message=%s "
        "diagnostic_refs=%s next_policy_decision=%s "
        "budget_after_attempted_compact=%s"
    )
    args = (
        request.session_id,
        request.run_id,
        request.trigger_source.value,
        rejected.attempt_number,
        rejected.failure_category.value,
        rejected.repairable,
        _exception_error_code(exception),
        _safe_exception_message(exception),
        ",".join(rejected.diagnostic_refs),
        rejected.next_policy_decision.value,
        rejected.budget_after_attempted_compact,
    )
    if rejected.repairable:
        _LOGGER.warning(log_message, *args)
    else:
        _LOGGER.error(log_message, *args)


def _exception_error_code(exc: Exception | None) -> str:
    """从 proposal 异常中提取可诊断错误码。

    :param exc: proposal 异常；无异常时为 ``None``。
    :returns: 机器可读错误码。
    :raises Exception: 不主动抛出异常。
    """

    if exc is None:
        return "none"
    match = _ERROR_CODE_PATTERN.search(str(exc))
    if match is not None:
        return match.group(1)
    return exc.__class__.__name__


def _safe_exception_message(exc: Exception | None) -> str:
    """构造脱敏 proposal 异常摘要。

    :param exc: proposal 异常；无异常时为 ``None``。
    :returns: 可进入日志的有界短文本。
    :raises Exception: 不主动抛出异常。
    """

    if exc is None:
        return "none"
    message = str(exc)
    if message.strip() == "":
        return exc.__class__.__name__
    redacted = redact_sensitive_diagnostic_values(
        message,
        redaction_marker=_REDACTED_SECRET,
    )
    return truncate_diagnostic_text(
        redacted,
        max_chars=_MAX_SAFE_EXCEPTION_MESSAGE_CHARS,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )


__all__ = [
    "CompactionAttemptRejected",
    "CompactionFailureCategory",
    "CompactionNextPolicyDecision",
    "CompactionOperationResult",
    "run_compaction_operation",
]
