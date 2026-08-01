"""Host 内部 context compaction operation helper。

本模块只执行事务外 compaction proposal attempt 循环、质量校验与 compact 后
预算硬阈值校验。EventLog 写入、artifact 写入、memory projection 与 durable
state recheck 仍由调用方所在的 Host governance 路径负责。
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from typing import Protocol, runtime_checkable
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.runner_identity import SuccessfulRunnerResponseIdentity
from dayu.engine.contracts.engine_events import RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
from dayu.host._runner_call_manifest import (
    RunnerCallHotAtoms,
    RunnerCallProjectorMetadata,
    complete_runner_call_hot_diagnostic,
    not_applicable_runner_call_sizing_snapshot,
    runner_call_hot_payload,
    runner_call_projector_metadata_descriptor,
    runner_call_sizing_snapshot_json,
)
from dayu.host.compact_material import conversation_compact_input_vnext_from_material_pack
from dayu.host.compact_payload import accepted_compact_business_texts
from dayu.host.compaction import (
    CompactMaterialBlock,
    CompactQualityCheckResultVNext,
    CompactionRequest,
    CompactorProposal,
    CompactorProposalError,
    ContextCompactor,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
)
from dayu.host.context_budget import estimate_post_compact_budget
from dayu.host.context_events import CompactorProposalManifestReference
from dayu.host.context_governance import check_conversation_compact_output_vnext
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.payload import BoundedJsonPayloadWriteRequest, PayloadStore
from dayu.host.durable.schema import (
    PayloadDescriptorKind,
    RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
    payload_descriptor_metadata,
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
_COMPACTION_REJECTED_DIAGNOSTIC_SCHEMA_VERSION = (
    "compaction_rejected_attempt_diagnostic.v1"
)
_COMPACTION_REJECTED_DIAGNOSTIC_MEDIA_TYPE = (
    "application/vnd.dayu.compaction-rejected-attempt-diagnostic+json"
)
_COMPACTION_REJECTED_DIAGNOSTIC_PAYLOAD_PREFIX = "compaction-diagnostic"
_EVENT_ID_COMPACTION_REJECTED_DIAGNOSTIC_PREFIX = (
    "event-compaction-rejected-diagnostic"
)
_EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED = (
    "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
)
_DIAGNOSTIC_STAGE_MATERIAL_PACK_TO_COMPACT_INPUT = (
    "material_pack_to_compact_input"
)
_DIAGNOSTIC_STAGE_PROPOSAL_EXECUTION = "proposal_execution"
_DIAGNOSTIC_PARSER_COMPACT_INPUT_PROJECTOR = (
    "conversation_compact_input_vnext_from_material_pack"
)
_DIAGNOSTIC_PARSER_PROPOSAL_EXECUTION = "compactor_proposal_execution"


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
    ) -> CompactorProposal:
        """执行已准备的 compactor proposal runner call。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: 与实际成功 Runner call 身份配对的 vNext proposal。
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
    :param event_source: 写入 EventLog 的 Host source。
    """

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore,
        event_source: str,
    ) -> None:
        """初始化 durable recorder。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog store。
        :param event_source: 写入 EventLog 的 Host source。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = event_log_store
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
            projection_descriptor = self._payload_store.write_bounded_json_payload(
                transaction,
                BoundedJsonPayloadWriteRequest(
                    payload_ref=projection_ref,
                    sqlite_payload_id=_compactor_input_projection_payload_id(
                        event_id
                    ),
                    payload_json=prepared_input.compactor_input_projection,
                    media_type=_COMPACTOR_INPUT_PROJECTION_MEDIA_TYPE,
                    metadata=payload_descriptor_metadata(
                        PayloadDescriptorKind.COMPACTOR_INPUT_PROJECTION,
                        {
                            "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                            "event_id": event_id,
                            "compaction_operation_id": compaction_operation_id,
                            "compaction_attempt_number": compaction_attempt_number,
                            "compaction_request_digest": (
                                prepared_input.compaction_request_digest
                            ),
                        },
                    ),
                    expected_digest=(
                        prepared_input.compactor_input_projection_digest
                    ),
                ),
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
            manifest_payload_ref = _runner_call_manifest_payload_ref(event_id)
            manifest_descriptor = self._payload_store.write_bounded_json_payload(
                transaction,
                BoundedJsonPayloadWriteRequest(
                    payload_ref=manifest_payload_ref,
                    sqlite_payload_id=_runner_call_manifest_payload_id(event_id),
                    payload_json=manifest,
                    media_type=RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
                    metadata=payload_descriptor_metadata(
                        PayloadDescriptorKind.RUNNER_CALL_INPUT_MANIFEST,
                        {
                            "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                            "event_id": event_id,
                            "schema_version": (
                                RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION
                            ),
                            "compaction_operation_id": compaction_operation_id,
                            "compaction_attempt_number": compaction_attempt_number,
                        },
                    ),
                    expected_digest=manifest_digest,
                ),
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
                compaction_operation_id=compaction_operation_id,
                compaction_attempt_number=compaction_attempt_number,
                compactor_engine_run_id=prepared_input.compactor_engine_run_id,
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
class CompactionRejectedAttemptOffendingBlock:
    """rejected attempt diagnostic 中定位到的 offending material block。

    :param section: material section。
    :param kind: material block kind。
    :param block_label: prompt-local block label。
    :param block_ordinal: block 在 previous compacted view 中的 0-based 序号。
    :param block_path: artifact 内稳定 locator path。
    :param content_digest: block content digest。
    :param text_digest: block text digest。
    :param text_length: block text 字符数。
    """

    section: str
    kind: str
    block_label: str
    block_ordinal: int
    block_path: str
    content_digest: str
    text_digest: str
    text_length: int


@dataclass(frozen=True, slots=True)
class CompactionRejectedAttemptDiagnostic:
    """rejected attempt 的内存态 diagnostic artifact body。

    该对象可包含 raw previous compacted view 文本，只能在 Host 内部传递，
    不得投影进 EventLog canonical payload、Conversation Memory、compact
    LLM input 或 ordinary RunInput。

    :param artifact_body: 将写入 diagnostic artifact 的 canonical JSON object。
    :param failure_category: 失败分类。
    :param failure_stage: 失败阶段。
    :param diagnostic_suffix: 与 diagnostic refs 对齐的诊断后缀。
    :param parser_or_validator: 失败来源 parser / validator。
    :param exception_class: 异常类型。
    :param exception_message: 已脱敏异常消息。
    :param offending_block: offending block locator；无法定位时为 ``None``。
    :param material_pack_digest: material pack digest。
    :param compaction_request_digest: compaction request digest。
    """

    artifact_body: Mapping[str, JsonValue]
    failure_category: CompactionFailureCategory
    failure_stage: str
    diagnostic_suffix: str
    parser_or_validator: str
    exception_class: str
    exception_message: str
    offending_block: CompactionRejectedAttemptOffendingBlock | None
    material_pack_digest: str
    compaction_request_digest: str


@dataclass(frozen=True, slots=True)
class CompactionRejectedAttemptDiagnosticReference:
    """已持久化 rejected attempt diagnostic artifact 引用。

    :param payload_ref: payload descriptor ref。
    :param payload_digest: artifact digest。
    :param artifact_relative_path: artifact root 下的相对路径。
    :param diagnostic: 原始内存态 diagnostic 摘要。
    """

    payload_ref: str
    payload_digest: str
    artifact_relative_path: str
    diagnostic: CompactionRejectedAttemptDiagnostic


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
    :param proposal_manifest_reference: 对应该 proposal attempt 的 typed manifest
        reference；尚未记录时为 ``None``。
    :param successful_response_identity: 本 attempt 获得成功 Engine final 时的
        同源响应身份；尚未取得成功 final 时为 ``None``。
    :param diagnostic: material / proposal failure diagnostic；没有额外
        artifact 时为 ``None``。
    """

    attempt_number: int
    failure_category: CompactionFailureCategory
    repairable: bool
    runner_attempt_summary_refs: tuple[str, ...]
    diagnostic_refs: tuple[str, ...]
    next_policy_decision: CompactionNextPolicyDecision
    budget_after_attempted_compact: int | None
    proposal_manifest_reference: CompactorProposalManifestReference | None
    successful_response_identity: SuccessfulRunnerResponseIdentity | None
    diagnostic: CompactionRejectedAttemptDiagnostic | None = None


@dataclass(frozen=True, slots=True)
class CompactionOperationResult:
    """事务外 compaction operation 结果。

    :param accepted_candidate: 被 Host 接受的 candidate；失败时为 ``None``。
    :param quality_result: accepted candidate 对应 quality result。
    :param rejected_attempts: semantic attempt reject 诊断列表。
    :param failure_reason: 最终失败原因；成功时为 ``None``。
    :param budget_after_attempted_compact: 最后一次 attempt 后预算；未知时为
        ``None``。
    :param accepted_attempt_number: 被接受的全局 attempt number；失败时为
        ``None``。
    :param accepted_proposal_manifest_reference: accepted proposal 对应的 typed
        manifest reference；失败时为 ``None``。
    :param accepted_successful_response_identity: accepted candidate 对应的实际
        成功 Engine final 身份；operation 失败时为 ``None``。
    """

    accepted_candidate: ConversationCompactOutputVNext | None
    quality_result: CompactQualityCheckResultVNext | None
    rejected_attempts: tuple[CompactionAttemptRejected, ...]
    failure_reason: str | None
    budget_after_attempted_compact: int | None
    accepted_attempt_number: int | None
    accepted_successful_response_identity: SuccessfulRunnerResponseIdentity | None
    accepted_proposal_manifest_reference: CompactorProposalManifestReference | None

    def required_successful_response_identity(
        self,
    ) -> SuccessfulRunnerResponseIdentity:
        """返回 accepted candidate 对应的成功响应身份。

        :returns: accepted candidate 对应的成功 Runner call 身份。
        :raises RuntimeError: accepted result 缺少成功响应身份时抛出。
        """

        value = self.accepted_successful_response_identity
        if value is None:
            raise RuntimeError(
                "accepted compaction is missing successful response identity"
            )
        return value

    def required_proposal_manifest_reference(
        self,
    ) -> CompactorProposalManifestReference:
        """返回 accepted proposal 对应的 typed manifest reference。

        :returns: accepted proposal 对应的 typed manifest reference。
        :raises RuntimeError: accepted result 缺少 manifest reference 时抛出。
        """

        value = self.accepted_proposal_manifest_reference
        if value is None:
            raise RuntimeError(
                "accepted compaction is missing proposal manifest reference"
            )
        return value


@dataclass(frozen=True, slots=True)
class _CompactorProposalAttempt:
    """单次 proposal attempt 执行结果。

    :param compact_input: quality check 使用的同源 compactor input。
    :param candidate: compactor 返回的 candidate。
    :param proposal_manifest_reference: 调用前写入的 manifest ref；未记录时为
        ``None``。
    :param successful_response_identity: 产生 candidate 的成功 Runner call 身份。
    """

    compact_input: ConversationCompactInputVNext
    candidate: ConversationCompactOutputVNext
    proposal_manifest_reference: CompactorProposalManifestReference | None
    successful_response_identity: SuccessfulRunnerResponseIdentity


@dataclass(frozen=True, slots=True)
class _CompactorProposalExecutionError(Exception):
    """proposal 执行失败并携带已写 manifest ref。

    :param original_exception: 原始 proposal 异常。
    :param proposal_manifest_reference: 已写 manifest ref。
    :param successful_response_identity: 失败发生在成功 Engine final 之后时的
        同源响应身份；否则为 ``None``。
    """

    original_exception: Exception
    proposal_manifest_reference: CompactorProposalManifestReference | None
    successful_response_identity: SuccessfulRunnerResponseIdentity | None


@dataclass(frozen=True, slots=True)
class _CompactorProposalCancelledError(Exception):
    """proposal 在 Host cancellation 生效后取消并携带 manifest ref。

    :param proposal_manifest_reference: 已写 manifest ref。
    """

    proposal_manifest_reference: CompactorProposalManifestReference | None


class _CompactionAttemptCancellationToken(CancellationToken):
    """单次 compactor proposal attempt 的 linked cancellation token。

    parent 保存 Run / reactive operation 的生命周期事实；本 token 只拥有当前
    provider attempt 的局部 timeout。每次 retry 必须新建实例，避免一次 timeout
    污染后续 repair attempt。读取时 parent cancellation 始终优先。

    :param parent: Host 注入的只读 parent cancellation token。
    """

    def __init__(self, parent: CancellationToken) -> None:
        """初始化未取消的 attempt-local 状态。

        :param parent: Host 注入的只读 parent cancellation token。
        :returns: ``None``。
        :raises TypeError: ``parent`` 不满足 cancellation 观察协议时抛出。
        """

        if not isinstance(parent, CancellationToken):
            raise TypeError("parent must implement CancellationToken")
        self._parent = parent
        self._lock = Lock()
        self._local_reason: str | None = None
        self._local_requested_at: datetime | None = None

    def is_cancelled(self) -> bool:
        """返回 parent 或当前 attempt 是否已请求取消。

        :returns: 任一 owner 已请求取消时返回 ``True``。
        :raises Exception: parent token 读取失败时原样抛出。
        """

        if self._parent.is_cancelled():
            return True
        with self._lock:
            return self._local_reason is not None

    def cancel_reason(self) -> str | None:
        """返回当前有效取消原因，并保证 parent 原因优先。

        :returns: parent 原因、attempt-local 原因或 ``None``。
        :raises Exception: parent token 读取失败时原样抛出。
        """

        parent_reason = self._parent.cancel_reason()
        if parent_reason is not None:
            return parent_reason
        with self._lock:
            return self._local_reason

    def requested_at(self) -> datetime | None:
        """返回当前有效取消请求时间，并保证 parent 时间优先。

        :returns: parent 时间、attempt-local 时间或 ``None``。
        :raises Exception: parent token 读取失败时原样抛出。
        """

        if self._parent.cancel_reason() is not None:
            return self._parent.requested_at()
        with self._lock:
            return self._local_requested_at

    def request_cancel(self, reason: str) -> None:
        """只取消当前 compactor proposal attempt。

        :param reason: attempt-local 结构化取消原因。
        :returns: ``None``。
        :raises ValueError: ``reason`` 为空时抛出。
        """

        if not reason:
            raise ValueError("reason must be non-empty")
        with self._lock:
            if self._local_reason is None:
                self._local_reason = reason
                self._local_requested_at = datetime.now(UTC)


async def run_compaction_operation(
    *,
    request: CompactionRequest,
    compactor: ContextCompactor,
    first_attempt_number: int,
    max_attempt_number: int,
    cancellation_token: CancellationToken,
    pass_queue: tuple[CompactionRequest, ...] = (),
    compaction_operation_id: str | None = None,
    proposal_manifest_recorder: CompactorProposalManifestRecorder | None = None,
) -> CompactionOperationResult:
    """在事务外执行 Host semantic compaction operation。

    :param request: Host compaction request。
    :param compactor: Host internal compactor seam。
    :param first_attempt_number: 本次执行的首个全局 proposal attempt number。
    :param max_attempt_number: operation 冻结的全局 proposal attempt 上限。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :param pass_queue: 同一 operation 内的 pass request 队列；为空时使用
        ``request`` 作为单 pass。
    :param compaction_operation_id: Host compaction operation id；生产路径必须传入。
    :param proposal_manifest_recorder: compactor proposal manifest 记录器。
    :returns: compaction operation 结果。
    """

    return await _run_compaction_operation(
        request=request,
        compactor=compactor,
        first_attempt_number=first_attempt_number,
        max_attempt_number=max_attempt_number,
        last_execution_attempt_number=max_attempt_number,
        cancellation_token=cancellation_token,
        pass_queue=pass_queue,
        compaction_operation_id=compaction_operation_id,
        proposal_manifest_recorder=proposal_manifest_recorder,
    )


async def run_compaction_attempt(
    *,
    request: CompactionRequest,
    compactor: ContextCompactor,
    attempt_number: int,
    max_attempt_number: int,
    cancellation_token: CancellationToken,
    compaction_operation_id: str | None = None,
    proposal_manifest_recorder: CompactorProposalManifestRecorder | None = None,
) -> CompactionOperationResult:
    """执行 single-operation 全局预算内的精确一次 semantic attempt。

    本 owner API 让 proactive dispatcher 为每个全局 attempt 选择对应 tier
    request，同时仍以 operation 的冻结上限派生 ``repairable`` 与下一 policy
    decision。reactive multi-pass 继续使用完整 ``run_compaction_operation``。

    :param request: 当前全局 attempt 对应的 Host compaction request。
    :param compactor: Host internal compactor seam。
    :param attempt_number: 当前 operation 的全局 attempt number。
    :param max_attempt_number: operation 冻结的全局 proposal attempt 上限。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :param compaction_operation_id: Host compaction operation id；生产路径必须传入。
    :param proposal_manifest_recorder: compactor proposal manifest 记录器。
    :returns: 只执行当前 attempt 的 operation result。
    :raises ValueError: attempt range 非法时抛出。
    """

    return await _run_compaction_operation(
        request=request,
        compactor=compactor,
        first_attempt_number=attempt_number,
        max_attempt_number=max_attempt_number,
        last_execution_attempt_number=attempt_number,
        cancellation_token=cancellation_token,
        pass_queue=(),
        compaction_operation_id=compaction_operation_id,
        proposal_manifest_recorder=proposal_manifest_recorder,
    )


async def _run_compaction_operation(
    *,
    request: CompactionRequest,
    compactor: ContextCompactor,
    first_attempt_number: int,
    max_attempt_number: int,
    last_execution_attempt_number: int,
    cancellation_token: CancellationToken,
    pass_queue: tuple[CompactionRequest, ...],
    compaction_operation_id: str | None,
    proposal_manifest_recorder: CompactorProposalManifestRecorder | None,
) -> CompactionOperationResult:
    """执行共享的 semantic attempt loop。

    :param request: Host compaction request。
    :param compactor: Host internal compactor seam。
    :param first_attempt_number: 本次 execution 首个全局 attempt number。
    :param max_attempt_number: operation 冻结的全局上限。
    :param last_execution_attempt_number: 当前调用允许执行的最后 attempt number。
    :param cancellation_token: Host 注入的真实取消 token。
    :param pass_queue: reactive multi-pass request 队列。
    :param compaction_operation_id: durable operation id。
    :param proposal_manifest_recorder: proposal manifest owner。
    :returns: compaction operation 结果。
    :raises ValueError: attempt range 非法时抛出。
    """

    if first_attempt_number <= 0:
        raise ValueError("first_attempt_number must be positive")
    if max_attempt_number <= 0:
        raise ValueError("max_attempt_number must be positive")
    if first_attempt_number > max_attempt_number:
        raise ValueError("first_attempt_number must not exceed max_attempt_number")
    if last_execution_attempt_number < first_attempt_number:
        raise ValueError(
            "last_execution_attempt_number must not precede first_attempt_number"
        )
    if last_execution_attempt_number > max_attempt_number:
        raise ValueError(
            "last_execution_attempt_number must not exceed max_attempt_number"
        )
    requests = _operation_pass_requests(request=request, pass_queue=pass_queue)
    rejected: list[CompactionAttemptRejected] = []
    last_budget: int | None = None
    accepted_candidate: ConversationCompactOutputVNext | None = None
    accepted_quality: CompactQualityCheckResultVNext | None = None
    accepted_manifest_reference: CompactorProposalManifestReference | None = None
    accepted_attempt_number: int | None = None
    accepted_successful_response_identity: (
        SuccessfulRunnerResponseIdentity | None
    ) = None
    attempt_number = first_attempt_number
    for pass_request in requests:
        pass_accepted = False
        while attempt_number <= last_execution_attempt_number and not pass_accepted:
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
                    successful_response_identity=None,
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
                    accepted_attempt_number=None,
                    accepted_successful_response_identity=None,
                    accepted_proposal_manifest_reference=None,
                )
            repairable = attempt_number < max_attempt_number
            next_decision = _NEXT_DECISION_RETRY_REPAIR if repairable else _NEXT_DECISION_FAIL_COMPACTION
            attempt_cancellation_token = _CompactionAttemptCancellationToken(
                cancellation_token
            )
            try:
                proposal = await _prepare_compactor_proposal(
                    compactor,
                    pass_request,
                    attempt_cancellation_token,
                    compaction_operation_id=compaction_operation_id,
                    compaction_attempt_number=attempt_number,
                    proposal_manifest_recorder=proposal_manifest_recorder,
                )
                compact_input = proposal.compact_input
                proposal_manifest_reference = proposal.proposal_manifest_reference
                candidate = proposal.candidate
            except _CompactorProposalExecutionError as exc:
                proposal_manifest_reference = exc.proposal_manifest_reference
                diagnostic_suffix = _exception_diagnostic_suffix(exc.original_exception)
                diagnostic = _proposal_failure_diagnostic(
                    request=pass_request,
                    compaction_operation_id=compaction_operation_id,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    diagnostic_suffix=diagnostic_suffix,
                    exception=exc.original_exception,
                    proposal_manifest_reference=proposal_manifest_reference,
                )
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=None,
                    diagnostic_suffix=diagnostic_suffix,
                    proposal_manifest_reference=proposal_manifest_reference,
                    successful_response_identity=(
                        exc.successful_response_identity
                    ),
                    diagnostic=diagnostic,
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
                        accepted_attempt_number=None,
                        accepted_successful_response_identity=None,
                        accepted_proposal_manifest_reference=None,
                    )
                attempt_number += 1
                continue
            except _CompactorProposalCancelledError as exc:
                proposal_manifest_reference = exc.proposal_manifest_reference
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_CANCELLATION_REQUESTED,
                    repairable=False,
                    next_policy_decision=_NEXT_DECISION_FAIL_COMPACTION,
                    budget_after_attempted_compact=last_budget,
                    diagnostic_suffix=_cancellation_suffix(cancellation_token),
                    proposal_manifest_reference=proposal_manifest_reference,
                    successful_response_identity=None,
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
                    accepted_attempt_number=None,
                    accepted_successful_response_identity=None,
                    accepted_proposal_manifest_reference=None,
                )
            except Exception as exc:
                diagnostic_suffix = _exception_diagnostic_suffix(exc)
                diagnostic = _proposal_failure_diagnostic(
                    request=pass_request,
                    compaction_operation_id=compaction_operation_id,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    diagnostic_suffix=diagnostic_suffix,
                    exception=exc,
                    proposal_manifest_reference=proposal_manifest_reference,
                )
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=None,
                    diagnostic_suffix=diagnostic_suffix,
                    proposal_manifest_reference=proposal_manifest_reference,
                    successful_response_identity=None,
                    diagnostic=diagnostic,
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
                        accepted_attempt_number=None,
                        accepted_successful_response_identity=None,
                        accepted_proposal_manifest_reference=None,
                    )
                attempt_number += 1
                continue
            quality = check_conversation_compact_output_vnext(compact_input, candidate)
            last_budget = estimate_post_compact_budget(
                compacted_business_texts=accepted_compact_business_texts(candidate),
                current_input_text=compact_input.current_input_anchor.text,
            )
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
                    successful_response_identity=(
                        proposal.successful_response_identity
                    ),
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
                        accepted_attempt_number=None,
                        accepted_successful_response_identity=None,
                        accepted_proposal_manifest_reference=None,
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
                    successful_response_identity=(
                        proposal.successful_response_identity
                    ),
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
                        accepted_attempt_number=None,
                        accepted_successful_response_identity=None,
                        accepted_proposal_manifest_reference=None,
                    )
                attempt_number += 1
                continue
            pass_accepted = True
            (
                accepted_candidate,
                accepted_quality,
                accepted_manifest_reference,
                accepted_attempt_number,
                accepted_successful_response_identity,
            ) = (
                candidate,
                quality,
                proposal_manifest_reference,
                attempt_number,
                proposal.successful_response_identity,
            )
            attempt_number += 1
        if not pass_accepted:
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=tuple(rejected),
                failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED.value,
                budget_after_attempted_compact=last_budget,
                accepted_attempt_number=None,
                accepted_successful_response_identity=None,
                accepted_proposal_manifest_reference=None,
            )
    if accepted_candidate is None or accepted_quality is None:
        return CompactionOperationResult(
            accepted_candidate=None,
            quality_result=None,
            rejected_attempts=tuple(rejected),
            failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED.value,
            budget_after_attempted_compact=last_budget,
            accepted_attempt_number=None,
            accepted_successful_response_identity=None,
            accepted_proposal_manifest_reference=None,
        )
    return CompactionOperationResult(
        accepted_candidate=accepted_candidate,
        quality_result=accepted_quality,
        rejected_attempts=tuple(rejected),
        failure_reason=None,
        budget_after_attempted_compact=last_budget,
        accepted_attempt_number=accepted_attempt_number,
        accepted_successful_response_identity=(
            accepted_successful_response_identity
        ),
        accepted_proposal_manifest_reference=accepted_manifest_reference,
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

    compaction owner 必须在接受 candidate 前统一执行 hard threshold 验收；
    proactive 与 reactive path 都不能把仍明显越界的 compact 输出交给下游
    dispatch / Engine event 循环处理。

    :param request: Host compaction request。
    :returns: 需要估算闸门时返回 ``True``。
    """

    del request
    return True


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
        _ensure_compactor_proposal_active(
            cancellation_token,
            proposal_manifest_reference=manifest_reference,
        )
        try:
            proposal = await compactor.run_prepared_compactor_proposal(
                prepared_input
            )
        except asyncio.CancelledError as exc:
            if not cancellation_token.is_cancelled():
                raise
            raise _CompactorProposalCancelledError(
                proposal_manifest_reference=manifest_reference,
            ) from exc
        except CompactorProposalError as exc:
            raise _CompactorProposalExecutionError(
                original_exception=exc,
                proposal_manifest_reference=manifest_reference,
                successful_response_identity=(
                    exc.successful_response_identity
                ),
            ) from exc
        except Exception as exc:
            raise _CompactorProposalExecutionError(
                original_exception=exc,
                proposal_manifest_reference=manifest_reference,
                successful_response_identity=None,
            ) from exc
        try:
            _validate_prepared_proposal_identity(
                prepared_input=prepared_input,
                proposal=proposal,
            )
        except CompactorProposalError as exc:
            raise _CompactorProposalExecutionError(
                original_exception=exc,
                proposal_manifest_reference=manifest_reference,
                successful_response_identity=(
                    exc.successful_response_identity
                ),
            ) from exc
        return _CompactorProposalAttempt(
            compact_input=prepared_input.compact_input,
            candidate=proposal.candidate,
            proposal_manifest_reference=manifest_reference,
            successful_response_identity=(
                proposal.successful_response_identity
            ),
        )
    compact_input = conversation_compact_input_vnext_from_material_pack(
        request.material_pack
    )
    _ensure_compactor_proposal_active(
        cancellation_token,
        proposal_manifest_reference=None,
    )
    try:
        proposal = await compactor.compact(request, cancellation_token)
    except asyncio.CancelledError as exc:
        if not cancellation_token.is_cancelled():
            raise
        raise _CompactorProposalCancelledError(
            proposal_manifest_reference=None,
        ) from exc
    except CompactorProposalError as exc:
        raise _CompactorProposalExecutionError(
            original_exception=exc,
            proposal_manifest_reference=None,
            successful_response_identity=exc.successful_response_identity,
        ) from exc
    return _CompactorProposalAttempt(
        compact_input=compact_input,
        candidate=proposal.candidate,
        proposal_manifest_reference=None,
        successful_response_identity=proposal.successful_response_identity,
    )


def _ensure_compactor_proposal_active(
    cancellation_token: CancellationToken,
    *,
    proposal_manifest_reference: CompactorProposalManifestReference | None,
) -> None:
    """在 provider 调用前重新确认本 attempt 仍可执行。

    prepared path 必须在 manifest recorder 返回后调用本函数，使 proactive
    durable parent 能重新读取 Run status 与 input cursor；失效时保留 manifest
    ref 作为诊断，但不得进入 provider。

    :param cancellation_token: 当前 attempt 的 linked cancellation token。
    :param proposal_manifest_reference: 已持久化的 manifest 引用。
    :returns: ``None``。
    :raises _CompactorProposalCancelledError: parent 或 attempt 已取消时抛出。
    :raises Exception: parent token 读取失败时原样抛出。
    """

    if cancellation_token.is_cancelled():
        raise _CompactorProposalCancelledError(
            proposal_manifest_reference=proposal_manifest_reference,
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
    reference = recorder.record_compactor_proposal_manifest(
        request=request,
        prepared_input=prepared_input,
        compaction_operation_id=compaction_operation_id,
        compaction_attempt_number=compaction_attempt_number,
    )
    if reference.compaction_operation_id != compaction_operation_id:
        raise ValueError("proposal manifest operation id mismatch")
    if reference.compaction_attempt_number != compaction_attempt_number:
        raise ValueError("proposal manifest attempt number mismatch")
    if reference.compactor_engine_run_id != prepared_input.compactor_engine_run_id:
        raise ValueError("proposal manifest compactor Engine run id mismatch")
    return reference


def _validate_prepared_proposal_identity(
    *,
    prepared_input: CompactorProposalRunInput,
    proposal: CompactorProposal,
) -> None:
    """校验 prepared proposal 与同一次成功 Engine call 绑定。

    :param prepared_input: 当前 Host attempt 冻结的 Engine request input。
    :param proposal: compactor 返回的 candidate/identity 配对值。
    :returns: 无返回值。
    :raises CompactorProposalError: Engine run、ordinary attempt/execution 或
        effective provider/model 与 prepared request 不一致时抛出。
    """

    response_identity = proposal.successful_response_identity
    request_identity = response_identity.runner_request_identity
    if request_identity.run_id != prepared_input.compactor_engine_run_id:
        raise CompactorProposalError(
            "compactor proposal Engine run identity mismatch",
            successful_response_identity=response_identity,
        )
    if request_identity.attempt_id is not None or request_identity.execution_id is not None:
        raise CompactorProposalError(
            "compactor proposal must not use ordinary attempt identity",
            successful_response_identity=response_identity,
        )
    runner_spec = prepared_input.agent_request.runner_spec
    if response_identity.effective_provider != runner_spec.provider:
        raise CompactorProposalError(
            "compactor proposal effective provider mismatch",
            successful_response_identity=response_identity,
        )
    if response_identity.effective_model != runner_spec.model:
        raise CompactorProposalError(
            "compactor proposal effective model mismatch",
            successful_response_identity=response_identity,
        )


def write_compaction_rejected_attempt_diagnostic_artifact(
    *,
    transaction: HostTransaction,
    artifact_store: LocalArtifactStore,
    payload_store: PayloadStore,
    diagnostic: CompactionRejectedAttemptDiagnostic,
    compaction_operation_id: str,
    compaction_attempt_number: int,
) -> CompactionRejectedAttemptDiagnosticReference:
    """在调用方事务内写入 rejected attempt diagnostic artifact descriptor。

    artifact 文件写入本身发生在文件系统；payload descriptor 插入使用调用方
    ``transaction``，以便与随后写入的 ``CONTEXT_COMPACTION_ATTEMPT_REJECTED``
    EventLog row 共享同一个 SQLite transaction。

    :param transaction: 调用方 Host transaction。
    :param artifact_store: 调用方显式创建的 artifact store。
    :param payload_store: payload descriptor store。
    :param diagnostic: 内存态 diagnostic body。
    :param compaction_operation_id: compaction operation id。
    :param compaction_attempt_number: proposal attempt 序号。
    :returns: 已持久化 diagnostic artifact 引用。
    :raises HostDurableError: descriptor 或 artifact 写入失败时抛出。
    """

    diagnostic_event_id = _new_event_id(
        _EVENT_ID_COMPACTION_REJECTED_DIAGNOSTIC_PREFIX
    )
    artifact_digest = sha256_digest_json(diagnostic.artifact_body)
    artifact_ref = artifact_store.write_artifact_bytes(
        canonical_json_dumps(diagnostic.artifact_body).encode("utf-8"),
        expected_digest=artifact_digest,
    )
    payload_ref = _compaction_rejected_diagnostic_payload_ref(diagnostic_event_id)
    descriptor = payload_store.write_payload_descriptor_for_artifact(
        transaction,
        payload_ref,
        artifact_ref,
        _COMPACTION_REJECTED_DIAGNOSTIC_MEDIA_TYPE,
        payload_descriptor_metadata(
            PayloadDescriptorKind.COMPACTION_REJECTED_ATTEMPT_DIAGNOSTIC,
            {
                "schema_version": _COMPACTION_REJECTED_DIAGNOSTIC_SCHEMA_VERSION,
                "event_type": _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                "diagnostic_event_id": diagnostic_event_id,
                "compaction_operation_id": compaction_operation_id,
                "compaction_attempt_number": compaction_attempt_number,
                "compaction_request_digest": diagnostic.compaction_request_digest,
                "failure_stage": diagnostic.failure_stage,
                "failure_category": diagnostic.failure_category.value,
                "exception_class": diagnostic.exception_class,
                "parser_or_validator": diagnostic.parser_or_validator,
                "contains_raw_material": True,
                "confidential": True,
            },
        ),
    )
    return CompactionRejectedAttemptDiagnosticReference(
        payload_ref=descriptor.payload_ref,
        payload_digest=descriptor.payload_digest,
        artifact_relative_path=artifact_ref.artifact_relative_path,
        diagnostic=diagnostic,
    )


def _new_event_id(prefix: str) -> str:
    """生成事件 id。

    :param prefix: id 前缀。
    :returns: 新事件 id。
    """

    return f"{prefix}-{uuid4().hex}"


def _compaction_rejected_diagnostic_payload_ref(diagnostic_event_id: str) -> str:
    """派生 rejected attempt diagnostic descriptor ref。

    :param diagnostic_event_id: diagnostic artifact event-like id。
    :returns: payload descriptor ref。
    """

    return f"{_COMPACTION_REJECTED_DIAGNOSTIC_PAYLOAD_PREFIX}:{diagnostic_event_id}"


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
        "memory_snapshot_cursor_ref": (
            None
            if request.memory_snapshot_cursor is None
            else f"memory:{request.memory_snapshot_cursor}"
        ),
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
        "sizing_snapshot": runner_call_sizing_snapshot_json(
            not_applicable_runner_call_sizing_snapshot()
        ),
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

    message_count = _required_manifest_int(manifest, "message_count")
    role_sequence_digest = _required_manifest_text(
        manifest,
        "role_sequence_digest",
    )
    return runner_call_hot_payload(
        RunnerCallHotAtoms(
            session_id=_required_manifest_text(manifest, "session_id"),
            host_run_id=_required_manifest_text(manifest, "host_run_id"),
            attempt_id=_optional_manifest_text(manifest, "attempt_id"),
            execution_id=_optional_manifest_text(manifest, "execution_id"),
            runner_call_index=_required_manifest_int(
                manifest, "runner_call_index"
            ),
            runner_call_kind=_required_manifest_text(
                manifest, "runner_call_kind"
            ),
            runner_call_trigger_reason=_required_manifest_text(
                manifest,
                "runner_call_trigger_reason",
            ),
            iteration_id=None,
            iteration_index=None,
            manifest_payload_ref=manifest_payload_ref,
            manifest_digest=manifest_digest,
            manifest_schema_version=_required_manifest_text(
                manifest, "schema_version"
            ),
            validation_status=_RUNNER_CALL_VALIDATION_COMPLETE,
            message_count=message_count,
            role_sequence_digest=role_sequence_digest,
            input_projection_digest=_required_manifest_text(
                manifest,
                "input_projection_digest",
            ),
            runner_call_projection_artifact_ref=None,
            runner_call_projection_artifact_digest=None,
            runner_call_projection_artifact_size_bytes=None,
            diagnostic=complete_runner_call_hot_diagnostic(
                status=_RUNNER_CALL_VALIDATION_COMPLETE,
                message_count=message_count,
                role_sequence_digest=role_sequence_digest,
                consumer_boundary=_GOVERNANCE_ACTOR,
            ),
        ),
        manifest=manifest,
    )


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
        runner_call_projector_metadata_descriptor(
            RunnerCallProjectorMetadata(
                projector_metadata_id=_compactor_projector_metadata_id(0),
                projector_id=_COMPACTOR_SYSTEM_PROJECTOR_ID,
                projector_schema_version=_COMPACTOR_PROJECTOR_SCHEMA_VERSION,
                projector_digest=prepared_input.system_prompt_asset_digest,
                purpose=_COMPACTOR_PROJECTOR_PURPOSE,
                source_contract_refs=(
                    f"prompt-digest:{prepared_input.system_prompt_asset_digest}",
                ),
            )
        ),
        runner_call_projector_metadata_descriptor(
            RunnerCallProjectorMetadata(
                projector_metadata_id=_compactor_projector_metadata_id(1),
                projector_id=_COMPACTOR_USER_PROJECTOR_ID,
                projector_schema_version=_COMPACTOR_PROJECTOR_SCHEMA_VERSION,
                projector_digest=prepared_input.user_prompt_digest,
                purpose=_COMPACTOR_PROJECTOR_PURPOSE,
                source_contract_refs=(
                    compactor_input_projection_ref,
                    *_compactor_source_cursor_refs(request),
                ),
            )
        ),
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


def _compactor_input_projection_payload_id(event_id: str) -> str:
    """派生 compactor input projection SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload row id。
    :raises Exception: 不主动抛出异常。
    """

    return f"sqlite:{_compactor_input_projection_ref(event_id)}"


def _runner_call_manifest_payload_ref(event_id: str) -> str:
    """派生 compactor runner-call manifest descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_RUNNER_CALL_MANIFEST_PAYLOAD_PREFIX}:{event_id}"


def _runner_call_manifest_payload_id(event_id: str) -> str:
    """派生 compactor runner-call manifest SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload row id。
    :raises Exception: 不主动抛出异常。
    """

    return f"sqlite:{_runner_call_manifest_payload_ref(event_id)}"


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


def _proposal_failure_diagnostic(
    *,
    request: CompactionRequest,
    compaction_operation_id: str | None,
    attempt_number: int,
    failure_category: CompactionFailureCategory,
    diagnostic_suffix: str,
    exception: Exception,
    proposal_manifest_reference: CompactorProposalManifestReference | None,
) -> CompactionRejectedAttemptDiagnostic | None:
    """构造 proposal failure 的内存态 diagnostic。

    该 helper 只生成 Host 内部 artifact body，不写文件、不写 SQLite，也不改变
    compact 决策。若 diagnostic 构造自身失败，返回 ``None`` 并保留原本的
    rejected attempt 行为。

    :param request: Host compaction request。
    :param compaction_operation_id: compaction operation id。
    :param attempt_number: proposal attempt 序号。
    :param failure_category: 失败分类。
    :param diagnostic_suffix: 与 diagnostic ref 对齐的后缀。
    :param exception: proposal / material projection 异常。
    :param proposal_manifest_reference: 已写 proposal manifest ref；没有时为
        ``None``。
    :returns: diagnostic；构造失败时返回 ``None``。
    """

    try:
        return _proposal_failure_diagnostic_unchecked(
            request=request,
            compaction_operation_id=compaction_operation_id,
            attempt_number=attempt_number,
            failure_category=failure_category,
            diagnostic_suffix=diagnostic_suffix,
            exception=exception,
            proposal_manifest_reference=proposal_manifest_reference,
        )
    except Exception as diagnostic_exc:
        _LOGGER.warning(
            "host.compaction_operation.diagnostic_build_failed "
            "session_id=%s run_id=%s operation_id=%s attempt_number=%s "
            "failure_category=%s error_code=%s message=%s",
            request.session_id,
            request.run_id,
            compaction_operation_id,
            attempt_number,
            failure_category.value,
            _exception_error_code(diagnostic_exc),
            _safe_exception_message(diagnostic_exc),
        )
        return None


def _proposal_failure_diagnostic_unchecked(
    *,
    request: CompactionRequest,
    compaction_operation_id: str | None,
    attempt_number: int,
    failure_category: CompactionFailureCategory,
    diagnostic_suffix: str,
    exception: Exception,
    proposal_manifest_reference: CompactorProposalManifestReference | None,
) -> CompactionRejectedAttemptDiagnostic:
    """构造 proposal failure diagnostic，错误由调用方兜底。

    :param request: Host compaction request。
    :param compaction_operation_id: compaction operation id。
    :param attempt_number: proposal attempt 序号。
    :param failure_category: 失败分类。
    :param diagnostic_suffix: 与 diagnostic ref 对齐的后缀。
    :param exception: proposal / material projection 异常。
    :param proposal_manifest_reference: 已写 proposal manifest ref。
    :returns: diagnostic。
    """

    exception_message = _safe_exception_message(exception)
    offending: CompactionRejectedAttemptOffendingBlock | None = None
    failure_stage, parser_or_validator = _proposal_failure_stage(
        exception_message=exception_message,
        proposal_manifest_reference=proposal_manifest_reference,
    )
    material_pack_digest = sha256_digest_json(
        {"material_pack": request.material_pack.to_json()}
    )
    compaction_request_digest = request.digest()
    artifact_body = _proposal_failure_diagnostic_artifact_body(
        request=request,
        compaction_operation_id=compaction_operation_id,
        attempt_number=attempt_number,
        failure_category=failure_category,
        diagnostic_suffix=diagnostic_suffix,
        exception=exception,
        exception_message=exception_message,
        proposal_manifest_reference=proposal_manifest_reference,
        failure_stage=failure_stage,
        parser_or_validator=parser_or_validator,
        offending_block=offending,
        material_pack_digest=material_pack_digest,
        compaction_request_digest=compaction_request_digest,
    )
    return CompactionRejectedAttemptDiagnostic(
        artifact_body=artifact_body,
        failure_category=failure_category,
        failure_stage=failure_stage,
        diagnostic_suffix=diagnostic_suffix,
        parser_or_validator=parser_or_validator,
        exception_class=exception.__class__.__name__,
        exception_message=exception_message,
        offending_block=offending,
        material_pack_digest=material_pack_digest,
        compaction_request_digest=compaction_request_digest,
    )


def _proposal_failure_stage(
    *,
    exception_message: str,
    proposal_manifest_reference: CompactorProposalManifestReference | None,
) -> tuple[str, str]:
    """返回 proposal failure 的稳定 stage 与 parser/validator 名称。

    :param exception_message: 已脱敏异常消息。
    :param proposal_manifest_reference: proposal manifest ref。
    :returns: ``(failure_stage, parser_or_validator)``。
    """

    del exception_message
    if proposal_manifest_reference is None:
        return (
            _DIAGNOSTIC_STAGE_MATERIAL_PACK_TO_COMPACT_INPUT,
            _DIAGNOSTIC_PARSER_COMPACT_INPUT_PROJECTOR,
        )
    return (
        _DIAGNOSTIC_STAGE_PROPOSAL_EXECUTION,
        _DIAGNOSTIC_PARSER_PROPOSAL_EXECUTION,
    )


def _proposal_failure_diagnostic_artifact_body(
    *,
    request: CompactionRequest,
    compaction_operation_id: str | None,
    attempt_number: int,
    failure_category: CompactionFailureCategory,
    diagnostic_suffix: str,
    exception: Exception,
    exception_message: str,
    proposal_manifest_reference: CompactorProposalManifestReference | None,
    failure_stage: str,
    parser_or_validator: str,
    offending_block: CompactionRejectedAttemptOffendingBlock | None,
    material_pack_digest: str,
    compaction_request_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 rejected attempt diagnostic artifact body。

    :param request: Host compaction request。
    :param compaction_operation_id: compaction operation id。
    :param attempt_number: proposal attempt 序号。
    :param failure_category: 失败分类。
    :param diagnostic_suffix: diagnostic ref 后缀。
    :param exception: 原始异常。
    :param exception_message: 已脱敏异常消息。
    :param proposal_manifest_reference: proposal manifest ref。
    :param failure_stage: 失败阶段。
    :param parser_or_validator: parser / validator 名称。
    :param offending_block: offending block locator。
    :param material_pack_digest: material pack digest。
    :param compaction_request_digest: compaction request digest。
    :returns: artifact JSON object。
    """

    previous_blocks = request.material_pack.previous_compacted_view
    return {
        "schema_version": _COMPACTION_REJECTED_DIAGNOSTIC_SCHEMA_VERSION,
        "event_type": _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        "session_id": request.session_id,
        "host_run_id": request.run_id,
        "attempt_id": request.attempt_id,
        "execution_id": request.execution_id,
        "input_snapshot_cursor": request.segment_selection.input_cursor,
        "memory_snapshot_cursor": request.memory_snapshot_cursor,
        "compaction_operation_id": compaction_operation_id,
        "compaction_attempt_number": attempt_number,
        "failure_stage": failure_stage,
        "failure_category": failure_category.value,
        "parser_or_validator": parser_or_validator,
        "exception_class": exception.__class__.__name__,
        "exception_message": exception_message,
        "diagnostic_suffix": diagnostic_suffix,
        "proposal_manifest_ref": (
            None
            if proposal_manifest_reference is None
            else proposal_manifest_reference.manifest_payload_ref
        ),
        "proposal_manifest_digest": (
            None
            if proposal_manifest_reference is None
            else proposal_manifest_reference.manifest_digest
        ),
        "material_pack_digest": material_pack_digest,
        "compaction_request_digest": compaction_request_digest,
        "contains_raw_material": True,
        "confidential": True,
        "previous_compacted_view": [block.to_json() for block in previous_blocks],
        "material_pack_summary": _material_pack_summary(request),
        "offending_block": _offending_block_artifact_json(
            previous_blocks=previous_blocks,
            offending_block=offending_block,
        ),
        "all_previous_compacted_view_blocks": [
            _previous_block_locator_json(block=block, ordinal=ordinal)
            for ordinal, block in enumerate(previous_blocks)
        ],
    }


def _material_pack_summary(request: CompactionRequest) -> Mapping[str, JsonValue]:
    """构造不含 raw trace/evidence/answer 文本的 material pack 摘要。

    :param request: Host compaction request。
    :returns: material pack 摘要。
    """

    anchor_text = request.material_pack.current_input_anchor.anchor_text
    return {
        "trace_material_count": len(request.material_pack.trace_material),
        "evidence_material_count": len(request.material_pack.evidence_material),
        "answer_material_count": len(request.material_pack.answer_material),
        "current_input_anchor_digest": (
            request.material_pack.current_input_anchor.content_digest
        ),
        "current_input_anchor_length": len(anchor_text),
    }


def _offending_block_artifact_json(
    *,
    previous_blocks: tuple[CompactMaterialBlock, ...],
    offending_block: CompactionRejectedAttemptOffendingBlock | None,
) -> Mapping[str, JsonValue] | None:
    """构造 artifact 中的 offending block JSON。

    :param previous_blocks: previous compacted view blocks。
    :param offending_block: offending block locator。
    :returns: JSON object；未定位时返回 ``None``。
    """

    if offending_block is None:
        return None
    if (
        offending_block.block_ordinal < 0
        or offending_block.block_ordinal >= len(previous_blocks)
    ):
        return None
    block = previous_blocks[offending_block.block_ordinal]
    return {
        "section": offending_block.section,
        "kind": offending_block.kind,
        "block_label": offending_block.block_label,
        "ordinal": offending_block.block_ordinal,
        "path": offending_block.block_path,
        "content_digest": offending_block.content_digest,
        "text_digest": offending_block.text_digest,
        "text_length": offending_block.text_length,
        "source_labels": list(block.source_labels),
        "canonical_source_refs": list(block.canonical_source_refs),
        "raw_text": block.text,
    }


def _previous_block_locator_json(
    *, block: CompactMaterialBlock, ordinal: int
) -> Mapping[str, JsonValue]:
    """构造 previous view block locator 摘要。

    :param block: previous view block。
    :param ordinal: block 序号。
    :returns: locator JSON object。
    """

    return {
        "section": block.section.value,
        "kind": block.kind.value,
        "block_label": block.block_label,
        "ordinal": ordinal,
        "path": f"previous_compacted_view[{ordinal}]",
        "content_digest": block.content_digest,
        "text_digest": _diagnostic_text_digest(block.text),
        "text_length": len(block.text),
        "source_labels": list(block.source_labels),
        "canonical_source_refs": list(block.canonical_source_refs),
    }


def _diagnostic_text_digest(text: str) -> str:
    """计算 diagnostic text digest。

    :param text: 文本。
    :returns: SHA-256 JSON digest。
    """

    return sha256_digest_json({"text": text})


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
    successful_response_identity: SuccessfulRunnerResponseIdentity | None,
    diagnostic: CompactionRejectedAttemptDiagnostic | None = None,
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
    :param successful_response_identity: 本 attempt 已取得成功 Engine final 时
        的同源响应身份；没有成功 final 时为 ``None``。
    :param diagnostic: material / proposal failure diagnostic。
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
        proposal_manifest_reference=proposal_manifest_reference,
        successful_response_identity=successful_response_identity,
        diagnostic=diagnostic,
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
        "budget_after_attempted_compact=%s failure_stage=%s "
        "diagnostic_suffix=%s parser_or_validator=%s exception_class=%s "
        "offending_block_kind=%s offending_block_label=%s "
        "offending_block_ordinal=%s offending_block_text_digest=%s "
        "offending_block_text_length=%s material_pack_digest=%s"
    )
    diagnostic = rejected.diagnostic
    offending = None if diagnostic is None else diagnostic.offending_block
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
        None if diagnostic is None else diagnostic.failure_stage,
        None if diagnostic is None else diagnostic.diagnostic_suffix,
        None if diagnostic is None else diagnostic.parser_or_validator,
        None if diagnostic is None else diagnostic.exception_class,
        None if offending is None else offending.kind,
        None if offending is None else offending.block_label,
        None if offending is None else offending.block_ordinal,
        None if offending is None else offending.text_digest,
        None if offending is None else offending.text_length,
        None if diagnostic is None else diagnostic.material_pack_digest,
    )
    _LOGGER.warning(log_message, *args)


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
    "run_compaction_attempt",
    "run_compaction_operation",
]
