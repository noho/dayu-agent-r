"""Host ToolRuntime 的 attempt-local typed ports。

本模块只落地 Phase 6 S1 需要的 ToolRuntime 装配边界：把外部业务
``ToolBundle`` 与可选 framework tool 注入合成为同一个
``EffectiveToolBundle``，并由 ``ToolRuntimeHandle`` 同时暴露 Engine
可见 schema 与批式 ``ToolExecutor``。本模块同时承载 Host accept
barrier、真实工具调用 wrapper、run-scoped truncation / ``fetch_more`` 普通
工具路径，以及 attempt-scoped in-memory duplicate governance。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, cast

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitSnapshot
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_execution import (
    AsyncDirectToolExecutionCapability,
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    ThreadBackedToolExecutionCapability,
    ToolExecutionCapability,
    ToolExecutionMode,
    ProcessToolCompletedEnvelope,
    ProcessToolFailedEnvelope,
    ProcessToolMalformedEnvelope,
    ProcessToolUnsupportedEnvelope,
    parse_process_tool_envelope,
)
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolAwaitingOutcome,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.contracts.tool_source import ToolBundleSourceRef
from dayu.host.accepted_tool_outcome import (
    accepted_tool_outcome_digest,
    accepted_tool_outcome_inline_size_bytes,
    accepted_tool_outcome_json,
)
from dayu.host.api import AttemptStatus, HostPayloadRef, RunStatus
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    is_sha256_digest,
    sha256_digest_json,
)
from dayu.host.durable.errors import (
    HostDurableError,
    HostIdempotencyConflictError,
    HostPayloadReferenceError,
    HostTransactionRetryExhaustedError,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.idempotency import (
    IdempotencyRecord,
    IdempotencyResultRef,
    IdempotencyResultKind,
    IdempotencyScope,
    IdempotencyScopeKind,
    IdempotencyStore,
)
from dayu.host.durable.payload import read_payload_descriptor
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    ExternalJobRef,
    RunRow,
    WaitResumePolicy,
    WaitSnapshotRef,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
    derive_accepted_evidence_id,
)
from dayu.host.projection import (
    ProjectionCatchupPort,
    catch_up_projection_best_effort,
)
from dayu.host.tool_trace_signals import (
    FAILURE_KIND_POLICY_BLOCKED as _FAILURE_KIND_POLICY_BLOCKED,
    FAILURE_KIND_TOOL_CANCELLED as _FAILURE_KIND_TOOL_CANCELLED,
    FAILURE_KIND_TOOL_FAILED as _FAILURE_KIND_TOOL_FAILED,
    FAILURE_METADATA_SCHEMA_VERSION as _FAILURE_METADATA_SCHEMA_VERSION,
    TOOL_TIMING_DURATION_SOURCE_META as _TOOL_TIMING_DURATION_SOURCE_META,
    TOOL_TIMING_SCHEMA_VERSION as _TOOL_TIMING_SCHEMA_VERSION,
    TOOL_TIMING_STATUS_AVAILABLE as _TOOL_TIMING_STATUS_AVAILABLE,
    TOOL_TIMING_STATUS_MISSING_META as _TOOL_TIMING_STATUS_MISSING_META,
    TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS as _TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS,
    bound_trace_signal_text,
)
from dayu.host.tool_call_request import (
    AcceptedToolCallRequestAtomInput,
    ToolCallRequestEventOrigin,
    build_tool_call_requested_event_request,
)
from dayu.runtime.cancellation import (
    WaitCancelled,
    WaitCompleted,
    WaitTimedOut,
    wait_for_or_cancel,
)
from dayu.runtime.interruptible_process import (
    InterruptibleProcessCompleted,
    InterruptibleProcessFailed,
    InterruptibleProcessHandle,
    InterruptibleProcessStillRunning,
    InterruptibleProcessTarget,
    ProcessInterruptResult,
)
from dayu.runtime.tool_truncation import effective_tool_truncate_spec
from dayu.host.tooling import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    ProcessCapsuleInterruptPolicy,
)
from dayu.host.tool_duplicate_governance import (
    DuplicateAcceptedEntry,
    DuplicateAwaitingAcceptedEntry,
    DuplicateDecision,
    DuplicateDecisionKind,
    DuplicateDurableMissingReason,
    DuplicateGovernancePolicy,
    DuplicateGovernancePort,
    DuplicateGovernanceRequest,
    DuplicateGovernanceScope,
    InMemoryAttemptDuplicateGovernance,
)
from dayu.host.tool_runtime_schema_projection import (
    business_bundle_digest as _business_bundle_digest,
)
from dayu.host.tool_runtime_schema_projection import (
    definitions_by_name as _definitions_by_name,
)
from dayu.host.tool_runtime_schema_projection import (
    tool_schemas_digest as _tool_schemas_digest,
)
from dayu.host.tool_runtime_schema_projection import (
    tool_schema_json as _tool_schema_json,
)
from dayu.host.tool_runtime_schema_projection import (
    validate_reserved_name_conflicts as _validate_reserved_name_conflicts,
)
from dayu.host.wait_adapter import (
    WaitActivationRegistry,
    WaitActivationRequest,
    WaitAdapterBinding,
    WaitAdapterRegistry,
)
from dayu.host.waiting import (
    HostToolAwaitingAcceptPort,
    ToolAwaitingAcceptCandidate,
    ToolAwaitingAcceptRejectReason,
    ToolAwaitingAcceptResult,
    ToolAwaitingAcceptTimedOut,
    ToolAwaitingAcceptedAck,
    ToolAwaitingEventRef,
    ToolAwaitingRejectedAck,
    build_tool_awaiting_accept_identity_digest,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOGGER = logging.getLogger(__name__)
_UNSUPPORTED_EXECUTOR_ERROR = "tool_runtime_not_connected"
_UNSUPPORTED_EXECUTOR_MESSAGE = (
    "ToolRuntime executor is not connected in Phase 6 S1"
)
_TOOL_FACT_ACCEPT_SCOPE_KIND = IdempotencyScopeKind.TOOL_FACT_ACCEPT
_TOOL_FACT_ACCEPT_RESULT_KIND = IdempotencyResultKind.TOOL_FACT_ACCEPT_ACK
_EVENT_ID_TOOL_CALL_REQUESTED_PREFIX = "event-tool-call-requested-"
_EVENT_ID_TOOL_CALL_GOVERNED_PREFIX = "event-tool-call-governed-"
_EVENT_ID_TOOL_RESULT_ACCEPTED_PREFIX = "event-tool-result-accepted-"
_EVENT_TYPE_TOOL_CALL_GOVERNED = "TOOL_CALL_GOVERNED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE = "accepted_evidence_envelope"
_PAYLOAD_FIELD_RAW_TOOL_OUTCOME = "raw_tool_outcome"
_PAYLOAD_FIELD_TOOL_TIMING = "tool_timing"
_PAYLOAD_FIELD_FAILURE_METADATA = "failure_metadata"
_TOOL_RESULT_PAYLOAD_REF_PREFIX = "payload-tool-result"
_TOOL_RESULT_SQLITE_PAYLOAD_ID_PREFIX = "sqlite-payload-tool-result"
_TOOL_ACCEPT_EVENT_ACTOR = "host.tool_runtime"
_TOOL_ACCEPT_EVENT_SOURCE = "host.tool_runtime.accept"
_MIN_ACCEPT_RETRY_ATTEMPTS = 1
_MIN_ACCEPT_BACKOFF_SECONDS = 0.0
_DEFAULT_ACCEPT_RETRY_ATTEMPTS = 2
_DEFAULT_ACCEPT_BACKOFF_SECONDS = 0.0
_TOOL_RESULT_SIZE_LOG_THRESHOLD_BYTES = 65536
_TOOL_RUNTIME_GOVERNED_ERROR = "host_tool_governed_error"
_TOOL_RUNTIME_POLICY_BLOCKED_ERROR = "tool_call_governed"
_TOOL_RUNTIME_ACCEPT_REJECTED_ERROR = "tool_accept_rejected"
_TOOL_RUNTIME_ACCEPT_TIMEOUT_ERROR = "tool_accept_timeout"
_TOOL_RUNTIME_AWAITING_ACCEPT_REJECTED_ERROR = "tool_awaiting_accept_rejected"
_TOOL_RUNTIME_AWAITING_ACCEPT_TIMEOUT_ERROR = "tool_awaiting_accept_timeout"
_TOOL_RUNTIME_UNKNOWN_TOOL_ERROR = "tool_not_found"
_TOOL_RUNTIME_CALLABLE_FAILED_ERROR = "tool_callable_failed"
_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR = "tool_capsule_build_failed"
_PROCESS_BACKED_TOOL_FAILED_ERROR = "process_backed_tool_failed"
_PROCESS_BACKED_TOOL_MALFORMED_ENVELOPE_ERROR = "process_backed_tool_malformed_envelope"
_PROCESS_BACKED_TOOL_UNSUPPORTED_ENVELOPE_ERROR = "process_backed_tool_unsupported_envelope"
_PROCESS_BACKED_TOOL_UNEXPECTED_PENDING_ERROR = "process_backed_tool_unexpected_pending"
_TOOL_RUNTIME_NO_TOOL_REASON = "tool_call_not_allowed_in_scope"
_TOOL_RUNTIME_IDEMPOTENCY_REASON = "tool_idempotency_key_required"
_TOOL_RUNTIME_UNSUPPORTED_AWAITING_REASON = "unsupported_awaiting"
_TOOL_RUNTIME_AWAITING_BINDING_REASON = "awaiting_adapter_not_configured"
_TOOL_RUNTIME_AWAITING_EXTERNAL_JOB_REASON = "awaiting_external_job_missing"
_TOOL_RUNTIME_AWAITING_BATCH_SUSPENDED_REASON = "run_suspended_by_tool_awaiting"
_TOOL_RUNTIME_CANCELLED_REASON = "tool_runtime_cancelled"
_TOOL_RUNTIME_TIMEOUT_REASON = "tool_runtime_timeout"
_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON = "accept_timeout"
_TOOL_RUNTIME_ACCEPT_REJECTED_REASON = "accept_rejected"
_TOOL_RUNTIME_ACCEPT_EXCEPTION_REASON = "accept_ack_lost"
_TOOL_RUNTIME_DUPLICATE_CLEANUP_FAILURE_REASON = "duplicate_cleanup_failed"
_TOOL_RUNTIME_DUPLICATE_AWAITING_MARKER_FAILURE_REASON = (
    "duplicate_awaiting_marker_failed"
)
_TOOL_RUNTIME_WAIT_ACTIVATION_FAILURE_REASON = "wait_activation_failed"
_TOOL_RUNTIME_DUPLICATE_REUSE_REASON = "duplicate_reuse"
_TOOL_RUNTIME_DUPLICATE_HINT_REASON = "duplicate_hint"
_TOOL_RUNTIME_DUPLICATE_REQUIRE_JUSTIFICATION_REASON = (
    "duplicate_requires_justification"
)
_TOOL_RUNTIME_DUPLICATE_HARD_STOP_REASON = "duplicate_hard_stop"
_TOOL_RUNTIME_DUPLICATE_AWAITING_FANOUT_REASON = "duplicate_awaiting_fanout"
_TOOL_RUNTIME_DIAGNOSTIC_NOOP_REF = "tool-diagnostic-noop"
_FAILURE_SIGNAL_SOURCE_TOOL_RESULT_ACCEPTED = _EVENT_TYPE_TOOL_RESULT_ACCEPTED
_ONE_MILLISECOND = timedelta(milliseconds=1)
_SIDE_EFFECT_IDEMPOTENCY_HINT = (
    "side-effect or paid tool requires a tool idempotency key"
)
_FETCH_MORE_DESCRIPTION = (
    "仅用于继续读取上一条被截断的工具结果；必须使用该结果给出的 "
    "cursor 与 scope_token，不能用于发起新的业务查询。"
)
_FETCH_MORE_CURSOR_FIELD = "cursor"
_FETCH_MORE_SCOPE_TOKEN_FIELD = "scope_token"
_FETCH_MORE_LIMIT_FIELD = "limit"
_TRUNCATED_VALUE_FIELD = "value"
_TRUNCATED_META_FIELD = "fetch_more"
_TRUNCATED_APPLIED_FIELD = "truncated"
_TRUNCATION_ERROR_CODE = "truncation_error"
_DEFAULT_TRUNCATION_TTL_SECONDS = 600
_DEFAULT_TEXT_CHARS_TRUNCATION_LIMIT = 4096
_DEFAULT_TEXT_LINES_TRUNCATION_LIMIT = 200
_DEFAULT_LIST_ITEMS_TRUNCATION_LIMIT = 100
_DEFAULT_BINARY_BYTES_TRUNCATION_LIMIT = 4096
_DEFAULT_TRUNCATION_LIMITS_BY_STRATEGY: Mapping[ToolTruncationStrategy, int] = {
    ToolTruncationStrategy.TEXT_CHARS: _DEFAULT_TEXT_CHARS_TRUNCATION_LIMIT,
    ToolTruncationStrategy.TEXT_LINES: _DEFAULT_TEXT_LINES_TRUNCATION_LIMIT,
    ToolTruncationStrategy.LIST_ITEMS: _DEFAULT_LIST_ITEMS_TRUNCATION_LIMIT,
    ToolTruncationStrategy.BINARY_BYTES: _DEFAULT_BINARY_BYTES_TRUNCATION_LIMIT,
}
_TRUNCATION_EXPIRED_CLEANUP_LIMIT = 64
_TRUNCATION_EXPIRED_CLEANUP_SCAN_LIMIT = 256
_MIN_TRUNCATION_LIMIT = 1
_TEXT_CHARS_LIMIT_KEY = "max_chars"
_TEXT_LINES_LIMIT_KEY = "max_lines"
_LIST_ITEMS_LIMIT_KEY = "max_items"
_BINARY_BYTES_LIMIT_KEY = "max_bytes"
class ToolPolicyDecisionKind(StrEnum):
    """工具治理决策类别。

    当前 slice 只定义后续端口会复用的稳定枚举，不实现决策算法。
    """

    ALLOW = "allow"
    GOVERNED_ERROR = "governed_error"
    REUSE = "reuse"
    HINT = "hint"
    REQUIRE_JUSTIFICATION = "require_justification"
    HARD_STOP = "hard_stop"


class ToolFactKind(StrEnum):
    """Host canonical 工具事实类别。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"
    REUSE = "reuse"
    GOVERNED_ERROR = "governed_error"


class ToolAcceptRejectReason(StrEnum):
    """Host accept barrier 拒绝原因。"""

    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_ATTEMPT = "invalid_attempt"
    STALE_EXECUTION = "stale_execution"
    SCHEMA_MISMATCH = "schema_mismatch"
    CAS_CONFLICT = "cas_conflict"
    EXPLICIT_POLICY_REJECT = "explicit_policy_reject"
    PAYLOAD_REFERENCE_INVALID = "payload_reference_invalid"


class ToolSideEffectKind(StrEnum):
    """工具副作用类别。

    ``READ_ONLY`` 工具不要求工具级幂等 key；``SIDE_EFFECT`` 与 ``PAID``
    工具必须由 Host 内部 policy 指定从哪个工具参数读取幂等 key。
    """

    READ_ONLY = "read_only"
    SIDE_EFFECT = "side_effect"
    PAID = "paid"


@dataclass(frozen=True, slots=True)
class ToolPolicyDecision:
    """工具调用治理决策。

    :param kind: 决策类别。
    :param reason_code: 机器可读原因；无原因时为 ``None``。
    :param message: 面向诊断或 LLM 的说明；无说明时为 ``None``。
    """

    kind: ToolPolicyDecisionKind
    reason_code: str | None
    message: str | None


@dataclass(frozen=True, slots=True)
class ToolInterruptStepResult:
    """单个 interrupt 步骤结果。

    :param supported: 当前 capsule 是否支持该步骤。
    :param completed: 步骤是否完成了对应资源中止。
    :param message: 诊断说明。
    """

    supported: bool
    completed: bool
    message: str


@dataclass(frozen=True, slots=True)
class HostEventRef:
    """Host EventLog 事件引用。

    :param event_id: EventLog 事件标识。
    :param event_sequence: EventLog 全局递增序号。
    """

    event_id: str
    event_sequence: int

    def __post_init__(self) -> None:
        """校验事件引用字段。

        :returns: ``None``。
        :raises ValueError: 事件标识为空或序号不是正数时抛出。
        """

        _require_non_empty_text(self.event_id, field_name="event_id")
        if self.event_sequence <= 0:
            raise ValueError("event_sequence must be positive")


@dataclass(frozen=True, slots=True)
class ToolTruncationFact:
    """工具结果截断事实。

    :param applied: 是否实际发生截断。
    :param strategy: 截断策略名称；未截断时为 ``None``。
    :param original_digest: 原始结果 digest；未截断时为 ``None``。
    :param truncated_digest: 截断后结果 digest；未截断时为 ``None``。
    :param cursor_hint: 可传给 ``fetch_more`` 的 cursor 提示；无则为 ``None``。
    """

    applied: bool
    strategy: str | None
    original_digest: str | None
    truncated_digest: str | None
    cursor_hint: str | None

    def __post_init__(self) -> None:
        """校验截断事实字段。

        :returns: ``None``。
        :raises ValueError: 截断字段组合不完整时抛出。
        """

        _require_optional_non_empty_text(self.strategy, field_name="strategy")
        _require_optional_sha256_digest(
            self.original_digest, field_name="original_digest"
        )
        _require_optional_sha256_digest(
            self.truncated_digest, field_name="truncated_digest"
        )
        _require_optional_non_empty_text(self.cursor_hint, field_name="cursor_hint")
        if self.applied and (
            self.strategy is None
            or self.original_digest is None
            or self.truncated_digest is None
        ):
            raise ValueError("applied truncation requires strategy and digests")


@dataclass(frozen=True, slots=True)
class ToolAcceptIdentity:
    """Host 工具事实 accept 的执行身份子结构。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: 构造完成的执行身份值对象。
    :raises ValueError: 任一身份字段为空时抛出。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str

    def __post_init__(self) -> None:
        """校验执行身份内部字段。

        :returns: ``None``。
        :raises ValueError: 任一身份字段为空时抛出。
        """

        _validate_tool_accept_identity(self)


@dataclass(frozen=True, slots=True)
class ToolAcceptCall:
    """Host 工具事实 accept 的工具调用子结构。

    :param iteration_id: Engine iteration id。
    :param tool_call_id: tool call id。
    :param tool_name: 工具名。
    :param accepted_arguments: 已被 Host accept 的 canonical 工具参数；仅构造
        fake ack 且不写 accepted fact 的低层测试可省略。
    :param tool_schema_digest: 工具 schema digest。
    :param tool_identity_digest: 工具身份 digest。
    :param normalized_arguments_digest: 规范化参数 digest。
    :param semantic_query_text: 可选业务可读 semantic query；缺失时为
        ``None``。
    :returns: 构造完成的工具调用值对象。
    :raises ValueError: 文本字段为空或 digest 非法时抛出。
    """

    iteration_id: str
    tool_call_id: str
    tool_name: str
    tool_schema_digest: str
    tool_identity_digest: str
    normalized_arguments_digest: str
    accepted_arguments: Mapping[str, JsonValue] | None = None
    semantic_query_text: str | None = None

    def __post_init__(self) -> None:
        """校验工具调用内部字段。

        :returns: ``None``。
        :raises ValueError: 文本字段为空或 digest 非法时抛出。
        """

        _validate_tool_accept_call(self)


@dataclass(frozen=True, slots=True)
class ToolAcceptResult:
    """Host 工具事实 accept 的结果子结构。

    :param outcome_digest: 工具 outcome digest。
    :param payload_digest: result payload digest；无 result payload 时为 ``None``。
    :param payload_ref: result payload descriptor 引用；无则为 ``None``。
    :param truncation: 截断事实；无截断时为 ``None``。
    :param raw_tool_outcome: Host accepted 后写入 raw transcript 的工具 outcome。
    :param tool_timing: 从工具 outcome meta 派生的稳定耗时 signal。
    :param failure_metadata: 从工具 outcome / governance 派生的失败 signal；成功时为
        ``None``。
    :returns: 构造完成的结果值对象。
    :raises ValueError: digest 非法、payload 引用不一致或截断事实类型非法时抛出。
    """

    outcome_digest: str
    payload_digest: str | None
    payload_ref: HostPayloadRef | None
    truncation: ToolTruncationFact | None
    raw_tool_outcome: JsonValue
    tool_timing: Mapping[str, JsonValue]
    failure_metadata: Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        """校验结果内部字段。

        :returns: ``None``。
        :raises ValueError: digest 非法、payload 引用不一致或截断事实类型非法时抛出。
        """

        _validate_tool_accept_result(self)


@dataclass(frozen=True, slots=True)
class ToolAcceptDuplicateGovernance:
    """Host 工具事实 accept 的 duplicate governance 子结构。

    :param duplicate_key: attempt-scoped duplicate key。
    :param duplicate_decision: duplicate governance 决策类别。
    :param duplicate_scope: duplicate governance 作用域。
    :param duplicate_decision_message: duplicate governance 决策消息。
    :param reuse_prior_event_refs: 可复用的既有 accepted event refs。
    :returns: 构造完成的 duplicate governance 值对象。
    :raises ValueError: duplicate 决策、key、scope、message 或 prior refs 非法时抛出。
    """

    duplicate_key: str | None
    duplicate_decision: DuplicateDecisionKind
    duplicate_scope: DuplicateGovernanceScope | None
    duplicate_decision_message: str | None
    reuse_prior_event_refs: tuple[HostEventRef, ...]

    def __post_init__(self) -> None:
        """校验 duplicate governance 内部字段。

        :returns: ``None``。
        :raises ValueError: duplicate 决策、key、scope、message 或 prior refs 非法时抛出。
        """

        _validate_tool_accept_duplicate_governance(self)


@dataclass(frozen=True, slots=True)
class ToolAcceptGovernance:
    """Host 工具事实 accept 的治理子结构。

    :param policy_decision: 工具调用治理决策。
    :param tool_idempotency_key: 工具自身幂等 key；无则为 ``None``。
    :param duplicate: duplicate governance 信息；无则为 ``None``。
    :returns: 构造完成的治理值对象。
    :raises ValueError: policy、工具幂等 key 或 duplicate governance 非法时抛出。
    """

    policy_decision: ToolPolicyDecision
    tool_idempotency_key: str | None
    duplicate: ToolAcceptDuplicateGovernance | None

    def __post_init__(self) -> None:
        """校验治理内部字段。

        :returns: ``None``。
        :raises ValueError: policy、工具幂等 key 或 duplicate governance 非法时抛出。
        """

        _validate_tool_accept_governance(self)


@dataclass(frozen=True, slots=True)
class ToolAcceptIdempotency:
    """Host 工具事实 accept 的幂等子结构。

    :param accept_idempotency_key: Host accept 幂等 key。
    :param semantic_input_digest: Host accept semantic input digest。
    :returns: 构造完成的幂等值对象。
    :raises ValueError: 幂等 key 为空或 semantic input digest 非法时抛出。
    """

    accept_idempotency_key: str
    semantic_input_digest: str

    def __post_init__(self) -> None:
        """校验幂等内部字段。

        :returns: ``None``。
        :raises ValueError: 幂等 key 为空或 semantic input digest 非法时抛出。
        """

        _validate_tool_accept_idempotency(self)


@dataclass(frozen=True, slots=True)
class ToolAcceptDiagnostics:
    """Host 工具事实 accept 的诊断子结构。

    :param diagnostic_refs: 工具诊断引用。
    :returns: 构造完成的诊断值对象。
    :raises ValueError: 任一诊断引用类型非法时抛出。
    """

    diagnostic_refs: tuple["ToolTraceDiagnosticRef", ...]

    def __post_init__(self) -> None:
        """校验诊断内部字段。

        :returns: ``None``。
        :raises ValueError: 任一诊断引用类型非法时抛出。
        """

        _validate_tool_accept_diagnostics(self)


@dataclass(frozen=True, slots=True)
class ToolFactAcceptCandidate:
    """Host accept barrier 的工具事实候选组合根。

    :param identity: accept precondition 与 EventLog row 使用的执行身份。
    :param call: 工具调用身份、schema 与参数 digest。
    :param tool_fact_kind: canonical 工具事实类别。
    :param result: 新 accepted result；reuse 不携带该结构。
    :param governance: policy 与 duplicate governance 信息。
    :param idempotency: Host accept 幂等信息。
    :param diagnostics: accept 诊断引用。
    :returns: 构造完成的工具事实候选组合根。
    :raises ValueError: 子结构类型或 fact kind 跨结构约束非法时抛出。
    """

    identity: ToolAcceptIdentity
    call: ToolAcceptCall
    tool_fact_kind: ToolFactKind
    result: ToolAcceptResult | None
    governance: ToolAcceptGovernance
    idempotency: ToolAcceptIdempotency
    diagnostics: ToolAcceptDiagnostics

    def __post_init__(self) -> None:
        """按工具事实类别校验候选字段。

        :returns: ``None``。
        :raises ValueError: 候选缺少必填字段或字段组合违反 fact kind 语义时抛出。
        """

        _validate_common_candidate_fields(self)
        _validate_duplicate_fields(self)
        if self.tool_fact_kind is ToolFactKind.COMPLETED:
            _validate_result_fact_policy(self)
            _require_raw_tool_outcome(self)
            _validate_candidate_failure_metadata(self, expected_kind=None)
            if _candidate_result(self).payload_digest is None:
                raise ValueError("completed requires payload_digest")
        elif self.tool_fact_kind in (ToolFactKind.FAILED, ToolFactKind.CANCELLED):
            _validate_result_fact_policy(self)
            _require_raw_tool_outcome(self)
            _validate_candidate_failure_metadata(
                self,
                expected_kind=(
                    _FAILURE_KIND_TOOL_FAILED
                    if self.tool_fact_kind is ToolFactKind.FAILED
                    else _FAILURE_KIND_TOOL_CANCELLED
                ),
            )
            if _candidate_reuse_prior_event_refs(self):
                raise ValueError(
                    f"{self.tool_fact_kind.value} must not carry prior reuse refs"
                )
        elif self.tool_fact_kind is ToolFactKind.GOVERNED_ERROR:
            _require_raw_tool_outcome(self)
            _validate_governed_error_candidate(self)
            _validate_candidate_failure_metadata(
                self,
                expected_kind=_FAILURE_KIND_POLICY_BLOCKED,
            )
        elif self.tool_fact_kind is ToolFactKind.REUSE:
            _validate_reuse_candidate(self)
        else:
            raise ValueError("unsupported tool_fact_kind")


@dataclass(frozen=True, slots=True)
class ToolFactAcceptedAck:
    """Host 已接受工具事实的 ack。

    :param accepted_event_refs: 本次 accept 关联的 EventLog refs。
    :param tool_fact_id: 稳定工具事实 id。
    :param tool_call_requested_event_ref: ``TOOL_CALL_REQUESTED`` event ref。
    :param tool_call_governed_event_ref: ``TOOL_CALL_GOVERNED`` event ref；无则为 ``None``。
    :param tool_result_event_ref: ``TOOL_RESULT_ACCEPTED`` event ref；reuse 时为 ``None``。
    :param result_payload_ref: result payload ref；无则为 ``None``。
    :param result_digest: result / semantic digest。
    :param reuse_prior_event_refs: reuse 指向的既有 accepted refs。
    :param diagnostic_refs: 工具诊断 refs。
    :param idempotency_record_ref: Host accept 幂等记录引用。
    """

    accepted_event_refs: tuple[HostEventRef, ...]
    tool_fact_id: str
    tool_call_requested_event_ref: HostEventRef
    tool_call_governed_event_ref: HostEventRef | None
    tool_result_event_ref: HostEventRef | None
    result_payload_ref: HostPayloadRef | None
    result_digest: str
    reuse_prior_event_refs: tuple[HostEventRef, ...]
    diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]
    idempotency_record_ref: str


@dataclass(frozen=True, slots=True)
class ToolFactRejectedAck:
    """Host 明确拒绝工具事实候选的 ack。

    :param reason_code: 拒绝原因码。
    :param message: 诊断说明。
    :param diagnostic_refs: 工具诊断 refs。
    :param retryable: 调用方是否可重试同一候选。
    """

    reason_code: ToolAcceptRejectReason
    message: str
    diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]
    retryable: bool


@dataclass(frozen=True, slots=True)
class ToolFactAcceptTimedOut:
    """Host accept barrier 未确认结果。

    :param attempt_count: 已尝试次数。
    :param last_error_code: 最后错误码；无则为 ``None``。
    :param diagnostic_refs: 工具诊断 refs。
    """

    attempt_count: int
    last_error_code: str | None
    diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]

    def __post_init__(self) -> None:
        """校验 timeout ack 字段。

        :returns: ``None``。
        :raises ValueError: 尝试次数非法或错误码为空白时抛出。
        """

        if self.attempt_count < _MIN_ACCEPT_RETRY_ATTEMPTS:
            raise ValueError("attempt_count must be positive")
        _require_optional_non_empty_text(
            self.last_error_code, field_name="last_error_code"
        )


def _default_tool_accept_retry_policy() -> "ToolAcceptRetryPolicy":
    """构造默认 accept ack 有限重试策略。

    :returns: 默认重试策略。
    """

    return ToolAcceptRetryPolicy(
        max_attempts=_DEFAULT_ACCEPT_RETRY_ATTEMPTS,
        backoff_seconds=_DEFAULT_ACCEPT_BACKOFF_SECONDS,
    )


@dataclass(frozen=True, slots=True)
class ToolAcceptRetryPolicy:
    """ToolRuntime accept ack 有限重试策略。

    :param max_attempts: 最大尝试次数。
    :param backoff_seconds: 每次重试前等待秒数。
    """

    max_attempts: int
    backoff_seconds: float

    def __post_init__(self) -> None:
        """校验重试策略字段。

        :returns: ``None``。
        :raises ValueError: 次数或 backoff 非法时抛出。
        """

        if self.max_attempts < _MIN_ACCEPT_RETRY_ATTEMPTS:
            raise ValueError("max_attempts must be positive")
        if self.backoff_seconds < _MIN_ACCEPT_BACKOFF_SECONDS:
            raise ValueError("backoff_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class ToolRuntimeExecutionScope:
    """ToolRuntime 执行期 attempt identity 与工具开关。

    :param session_id: 当前 Attempt 所属 Session id。
    :param run_id: 当前 Attempt 所属 Run id。
    :param attempt_id: 当前 Attempt id。
    :param execution_id: 当前 Attempt execution id。
    :param allow_tool_calls: 当前执行范围是否允许工具调用；replay / no-tool
        防线传入 ``False``。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    allow_tool_calls: bool

    def __post_init__(self) -> None:
        """校验执行范围字段。

        :returns: ``None``。
        :raises ValueError: 任一 identity 为空时抛出。
        """

        _require_non_empty_text(self.session_id, field_name="session_id")
        _require_non_empty_text(self.run_id, field_name="run_id")
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.execution_id, field_name="execution_id")


@dataclass(frozen=True, slots=True)
class ToolRuntimeToolPolicy:
    """单工具 Host 内部执行 policy。

    :param side_effect_kind: 工具副作用类别。
    :param idempotency_key_argument_name: ``SIDE_EFFECT`` / ``PAID`` 工具从
        哪个工具参数读取工具级幂等 key；read-only 工具为 ``None``。
    :param semantic_duplicate_key_argument_name: 工具可选提供的 attempt-local
        语义重复 key 参数名；无则为 ``None``。
    """

    side_effect_kind: ToolSideEffectKind
    idempotency_key_argument_name: str | None
    semantic_duplicate_key_argument_name: str | None = None

    def __post_init__(self) -> None:
        """校验单工具 policy 字段。

        :returns: ``None``。
        :raises ValueError: 副作用 / 付费工具缺少幂等 key 参数绑定时抛出。
        """

        _require_optional_non_empty_text(
            self.idempotency_key_argument_name,
            field_name="idempotency_key_argument_name",
        )
        _require_optional_non_empty_text(
            self.semantic_duplicate_key_argument_name,
            field_name="semantic_duplicate_key_argument_name",
        )
        if (
            self.side_effect_kind
            in (ToolSideEffectKind.SIDE_EFFECT, ToolSideEffectKind.PAID)
            and self.idempotency_key_argument_name is None
        ):
            raise ValueError(
                "side-effect or paid tool policy requires idempotency binding"
            )


@dataclass(frozen=True, slots=True)
class ToolRuntimePolicyView:
    """ToolRuntime Host 内部 policy view。

    :param rules_by_tool_name: 按工具名索引的 policy；未列出的工具按
        read-only 处理。
    """

    rules_by_tool_name: Mapping[str, ToolRuntimeToolPolicy] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """校验 policy view 字段。

        :returns: ``None``。
        :raises ValueError: 工具名为空时抛出。
        """

        for tool_name in self.rules_by_tool_name:
            _require_non_empty_text(tool_name, field_name="tool policy tool_name")

    def rule_for_tool(self, tool_name: str) -> ToolRuntimeToolPolicy:
        """返回指定工具的 policy rule。

        :param tool_name: 工具名。
        :returns: 工具 policy；未配置时返回 read-only policy。
        """

        rule = self.rules_by_tool_name.get(tool_name)
        if rule is not None:
            return rule
        return ToolRuntimeToolPolicy(
            side_effect_kind=ToolSideEffectKind.READ_ONLY,
            idempotency_key_argument_name=None,
            semantic_duplicate_key_argument_name=None,
        )


ToolFactAcceptResult = (
    ToolFactAcceptedAck | ToolFactRejectedAck | ToolFactAcceptTimedOut
)


@dataclass(frozen=True, slots=True)
class TextCharsRemainderRef:
    """按字符截断后的剩余文本引用。

    :param remaining_text: 未返回给 LLM 的剩余文本。
    :param digest: 剩余文本 digest。
    """

    remaining_text: str
    digest: str

    def __post_init__(self) -> None:
        """校验剩余文本引用字段。

        :returns: ``None``。
        :raises ValueError: digest 非法时抛出。
        """

        _require_sha256_digest(self.digest, field_name="text_chars_remainder_digest")


@dataclass(frozen=True, slots=True)
class TextLinesRemainderRef:
    """按行截断后的剩余文本行引用。

    :param remaining_lines: 未返回给 LLM 的剩余文本行。
    :param digest: 剩余行 digest。
    """

    remaining_lines: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        """校验剩余行引用字段。

        :returns: ``None``。
        :raises ValueError: digest 非法时抛出。
        """

        _require_sha256_digest(self.digest, field_name="text_lines_remainder_digest")


@dataclass(frozen=True, slots=True)
class ListItemsRemainderRef:
    """按列表项截断后的剩余 JSON 项引用。

    :param remaining_items: 未返回给 LLM 的剩余 JSON 项。
    :param digest: 剩余列表项 digest。
    """

    remaining_items: tuple[JsonValue, ...]
    digest: str

    def __post_init__(self) -> None:
        """校验剩余列表项引用字段。

        :returns: ``None``。
        :raises ValueError: digest 非法时抛出。
        """

        _require_sha256_digest(self.digest, field_name="list_items_remainder_digest")


@dataclass(frozen=True, slots=True)
class BinaryBytesRemainderRef:
    """按字节截断后的剩余二进制引用。

    ``remaining_bytes`` 是内存态能力的一部分，不进入 LLM-facing JSON；
    ``fetch_more`` 返回时会投影为 base64 ASCII 字符串。

    :param remaining_bytes: 未返回给 LLM 的剩余字节。
    :param digest: 剩余字节 digest。
    """

    remaining_bytes: bytes
    digest: str

    def __post_init__(self) -> None:
        """校验剩余字节引用字段。

        :returns: ``None``。
        :raises ValueError: digest 非法时抛出。
        """

        _require_sha256_digest(self.digest, field_name="binary_bytes_remainder_digest")


TruncatedRemainderRef = (
    TextCharsRemainderRef
    | TextLinesRemainderRef
    | ListItemsRemainderRef
    | BinaryBytesRemainderRef
)
"""截断剩余内容的封闭强类型联合。"""


@dataclass(frozen=True, slots=True)
class ToolTruncationCursor:
    """run-scoped 截断 cursor。

    :param cursor_id: 不透明 cursor id。
    :param scope_token_digest: scope token digest。
    :param session_id: cursor 所属 Session id。
    :param run_id: cursor 所属 Run id。
    :param attempt_id: cursor 所属 Attempt id。
    :param tool_call_id: 产生 cursor 的工具调用 id。
    :param tool_name: 产生 cursor 的工具名。
    :param strategy: 截断策略。
    :param created_at: cursor 创建时间。
    :param expires_at: cursor 过期时间。
    :param remaining_ref: 剩余内容引用。
    :param single_use: 是否单次使用。
    :param used_at: 使用时间；未使用时为 ``None``。
    """

    cursor_id: str
    scope_token_digest: str
    session_id: str
    run_id: str
    attempt_id: str
    tool_call_id: str
    tool_name: str
    strategy: ToolTruncationStrategy
    created_at: datetime
    expires_at: datetime
    remaining_ref: TruncatedRemainderRef
    single_use: bool
    used_at: datetime | None

    def __post_init__(self) -> None:
        """校验 cursor 字段。

        :returns: ``None``。
        :raises ValueError: identity 为空、digest 非法或时间非法时抛出。
        """

        for field_name, value in (
            ("cursor_id", self.cursor_id),
            ("session_id", self.session_id),
            ("run_id", self.run_id),
            ("attempt_id", self.attempt_id),
            ("tool_call_id", self.tool_call_id),
            ("tool_name", self.tool_name),
        ):
            _require_non_empty_text(value, field_name=field_name)
        _require_sha256_digest(
            self.scope_token_digest, field_name="scope_token_digest"
        )
        if self.expires_at < self.created_at:
            raise ValueError("expires_at must not be earlier than created_at")


@dataclass(frozen=True, slots=True)
class FetchMoreRequest:
    """``fetch_more`` 工具请求契约。

    :param cursor: 截断结果中返回的不透明 cursor。
    :param scope_token: 截断结果中返回的 scope token。
    :param limit: 可选补读上限；无则返回全部剩余内容。
    """

    cursor: str
    scope_token: str
    limit: int | None

    def __post_init__(self) -> None:
        """校验 ``fetch_more`` 请求字段。

        :returns: ``None``。
        :raises ValueError: cursor / token 为空或 limit 非正时抛出。
        """

        _require_non_empty_text(self.cursor, field_name="cursor")
        _require_non_empty_text(self.scope_token, field_name="scope_token")
        if self.limit is not None and self.limit < _MIN_TRUNCATION_LIMIT:
            raise ValueError("limit must be positive when provided")


FetchMoreResult = ToolCompletedOutcome | ToolFailedOutcome
"""``fetch_more`` 只返回普通 completed / failed 工具结果。"""


@dataclass(frozen=True, slots=True)
class TruncationAppliedOutcome:
    """截断端口输出。

    :param outcome: 可能已被截断改写的工具 outcome。
    :param cursor_hint: 普通工具结果中可提示 ``fetch_more`` 的 cursor；无为 ``None``。
    :param fact: 可写入 Host canonical fact 的截断事实；未截断时为 ``None``。
    """

    outcome: ToolExecutionOutcome
    cursor_hint: str | None
    fact: ToolTruncationFact | None


@dataclass(frozen=True, slots=True)
class _InlineToolResultGovernance:
    """LLM inline 工具结果大小治理输出。

    :param outcome: 可安全返回给 Engine 的工具 outcome。
    :param policy_decision: 与 outcome 匹配的治理决策。
    :param diagnostic_refs: 本次治理产生的诊断 refs。
    """

    outcome: ToolExecutionOutcome
    policy_decision: ToolPolicyDecision
    diagnostic_refs: tuple["ToolTraceDiagnosticRef", ...]


@dataclass(frozen=True, slots=True)
class _AwaitingAcceptExecution:
    """awaiting accept path 的内部返回值。

    :param record: 返回给 Engine 的单次工具执行记录。
    :param duplicate_terminal_recorded: duplicate terminal 是否已处理。
    :param durable_missing_reason: awaiting accept 未 accepted 时的 duplicate cleanup 原因。
    """

    record: BatchToolExecutionRecord
    duplicate_terminal_recorded: bool
    durable_missing_reason: DuplicateDurableMissingReason | None


@dataclass(frozen=True, slots=True)
class ToolTraceDiagnosticRecord:
    """ToolRuntime 诊断记录。

    :param reason_code: 诊断机器码。
    :param message: 人类可读诊断说明。
    """

    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class ToolTraceDiagnosticRef:
    """ToolRuntime 诊断引用。

    :param ref_id: 诊断记录引用 id。
    """

    ref_id: str


class FrameworkToolInjector(Protocol):
    """framework tool 注入 hook 协议。"""

    def build_framework_tool(self, tool_name: FrameworkToolName) -> ToolDefinition:
        """构造指定 framework tool 的声明。

        :param tool_name: framework tool 名称。
        :returns: 对应工具声明。
        :raises ValueError: 不支持指定 framework tool 时抛出。
        """
        ...


class ToolDispatcher(Protocol):
    """单工具 dispatch 端口协议。"""

    async def dispatch_tool_call(
        self, call: ToolCallRequest, context: BatchToolExecutionContext
    ) -> ToolExecutionOutcome:
        """分发单次工具调用。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行共享上下文。
        :returns: 工具执行 outcome。
        :raises Exception: 实现可抛出运行期异常，由 ToolRuntime 外层归一。
        """
        ...


class ToolExecutionCapsule(Protocol):
    """单工具调用执行资源 capsule 协议。"""

    @property
    def mode(self) -> ToolExecutionMode:
        """返回 capsule 执行模式。

        :returns: 执行模式。
        """

        ...

    async def run(self) -> ToolExecutionOutcome:
        """运行工具调用。

        :returns: 工具执行 outcome。
        """

        ...

    def request_interrupt(self, reason: str) -> None:
        """请求协作式 interrupt。

        :param reason: 诊断原因。
        :returns: ``None``。
        """

        ...

    async def terminate(self, reason: str) -> ToolInterruptStepResult:
        """请求 graceful terminate。

        :param reason: 诊断原因。
        :returns: terminate 步骤结果。
        """

        ...

    async def kill(self, reason: str) -> ToolInterruptStepResult:
        """请求 hard kill。

        :param reason: 诊断原因。
        :returns: kill 步骤结果。
        """

        ...

    async def close(self) -> None:
        """幂等释放 capsule 本地资源。

        :returns: ``None``。
        """

        ...


class ToolExecutionCapsuleFactory(Protocol):
    """单工具调用 execution capsule factory 协议。"""

    def create_capsule(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> ToolExecutionCapsule:
        """为单次工具调用创建 execution capsule。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 当前 ToolRuntime dispatcher。
        :returns: execution capsule。
        """

        ...


class ToolRuntimePolicyPort(Protocol):
    """ToolRuntime 治理决策端口协议。"""

    def decide_tool_call(self, call: ToolCallRequest) -> ToolPolicyDecision:
        """为单次工具调用生成治理决策。

        :param call: 单次工具调用请求。
        :returns: 治理决策。
        """
        ...


class TruncationPort(Protocol):
    """工具结果截断端口协议。"""

    def apply_truncation(
        self,
        tool_name: str,
        tool_call_id: str,
        outcome: ToolExecutionOutcome,
        truncate_spec: ToolTruncateSpec | None,
    ) -> TruncationAppliedOutcome:
        """应用工具结果截断策略。

        :param tool_name: 工具名。
        :param tool_call_id: 当前工具调用 id。
        :param outcome: 原始工具 outcome。
        :param truncate_spec: effective bundle 中同名工具的截断声明。
        :returns: 截断后的 outcome 与 cursor hint。
        """
        ...


class HostToolFactAcceptPort(Protocol):
    """工具 canonical fact accept barrier 端口协议。"""

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """接受工具事实候选。

        :param candidate: 工具事实候选。
        :returns: accepted / rejected / timeout 结构化结果。
        """
        ...


class ToolTraceDiagnosticEmitter(Protocol):
    """ToolRuntime 诊断发射端口协议。"""

    def emit(self, record: ToolTraceDiagnosticRecord) -> ToolTraceDiagnosticRef:
        """发出一条诊断记录。

        :param record: 诊断记录。
        :returns: 诊断引用。
        """
        ...


class DefaultToolDispatcher:
    """基于 ``EffectiveToolBundle`` 的默认单工具 dispatcher。"""

    def __init__(self, effective_bundle: "EffectiveToolBundle") -> None:
        """初始化 dispatcher。

        :param effective_bundle: 当前 attempt-local effective bundle。
        :returns: ``None``。
        """

        self._effective_bundle = effective_bundle

    async def dispatch_tool_call(
        self, call: ToolCallRequest, context: BatchToolExecutionContext
    ) -> ToolExecutionOutcome:
        """查找并异步调用业务工具，异常归一为工具失败。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 工具执行 outcome。
        """

        definition = self._effective_bundle.definitions_by_name.get(call.name)
        if definition is None:
            return _tool_failed_outcome(
                error=_TOOL_RUNTIME_UNKNOWN_TOOL_ERROR,
                message=f"tool is not available: {call.name}",
                hint=None,
            )
        try:
            return await definition.callable(call, context)
        except Exception as exc:
            return _tool_failed_outcome(
                error=_TOOL_RUNTIME_CALLABLE_FAILED_ERROR,
                message=f"{exc.__class__.__name__}: {exc}",
                hint=None,
            )


class AsyncDirectToolExecutionCapsule:
    """直接 async 工具执行 capsule。"""

    def __init__(
        self,
        *,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> None:
        """初始化 async direct capsule。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 当前 ToolRuntime dispatcher。
        :returns: ``None``。
        """

        self._call = call
        self._context = context
        self._dispatcher = dispatcher
        self._task: asyncio.Task[ToolExecutionOutcome] | None = None

    @property
    def mode(self) -> ToolExecutionMode:
        """返回执行模式。

        :returns: ``async_direct``。
        """

        return ToolExecutionMode.ASYNC_DIRECT

    async def run(self) -> ToolExecutionOutcome:
        """启动并等待 async 工具 callable。

        :returns: 工具执行 outcome。
        """

        if self._task is not None:
            raise RuntimeError("async direct capsule has already started")
        self._task = asyncio.create_task(
            self._dispatcher.dispatch_tool_call(self._call, self._context)
        )
        return await self._task

    def request_interrupt(self, reason: str) -> None:
        """取消正在等待的 async 工具 task。

        :param reason: 诊断原因。
        :returns: ``None``。
        """

        del reason
        task = self._task
        if task is not None and not task.done():
            task.cancel()

    async def terminate(self, reason: str) -> ToolInterruptStepResult:
        """async direct terminate 等价于取消当前 task。

        :param reason: 诊断原因。
        :returns: terminate 结果。
        """

        self.request_interrupt(reason)
        return ToolInterruptStepResult(
            supported=True,
            completed=True,
            message="async direct task cancellation requested",
        )

    async def kill(self, reason: str) -> ToolInterruptStepResult:
        """async direct 不支持 hard kill。

        :param reason: 诊断原因。
        :returns: unsupported kill 结果。
        """

        del reason
        return ToolInterruptStepResult(
            supported=False,
            completed=False,
            message="async direct capsule does not support hard kill",
        )

    async def close(self) -> None:
        """释放 async task 资源。

        :returns: ``None``。
        """

        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return


class DefaultToolExecutionCapsuleFactory:
    """默认 async direct capsule factory。"""

    def create_capsule(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> ToolExecutionCapsule:
        """创建默认 async direct capsule。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 当前 ToolRuntime dispatcher。
        :returns: async direct capsule。
        """

        return AsyncDirectToolExecutionCapsule(
            call=call,
            context=context,
            dispatcher=dispatcher,
        )


@dataclass(frozen=True, slots=True)
class _ThreadBackedDispatchTarget:
    """在线程中运行默认工具 dispatcher 的同步目标。"""

    call: ToolCallRequest
    context: BatchToolExecutionContext
    dispatcher: ToolDispatcher

    def __call__(self) -> ToolExecutionOutcome:
        """在当前线程的新事件循环中运行工具 dispatcher。

        :returns: 工具执行 outcome。
        :raises Exception: dispatcher 抛出的异常透传给 capsule 外层归一。
        """

        return asyncio.run(self.dispatcher.dispatch_tool_call(self.call, self.context))


class DeclaredToolExecutionCapsuleFactory:
    """基于工具声明 execution capability 创建执行 capsule 的 factory。"""

    def __init__(
        self,
        effective_bundle: "EffectiveToolBundle",
        process_capsule_interrupt_policy: ProcessCapsuleInterruptPolicy,
    ) -> None:
        """初始化 declaration-backed factory。

        :param effective_bundle: attempt-local effective 工具集合。
        :param process_capsule_interrupt_policy: process-backed capsule cleanup
            interrupt 策略。
        :returns: ``None``。
        """

        self._definitions_by_name = effective_bundle.definitions_by_name
        self._process_capsule_interrupt_policy = process_capsule_interrupt_policy

    def create_capsule(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        dispatcher: ToolDispatcher,
    ) -> ToolExecutionCapsule:
        """按 ``ToolDefinition.execution`` 创建单工具 execution capsule。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param dispatcher: 当前 ToolRuntime dispatcher。
        :returns: 与工具声明匹配的 execution capsule。
        :raises ValueError: 工具声明缺失时抛出。
        :raises TypeError: execution capability 类型未知时抛出。
        :raises Exception: process target factory 构造目标失败时透传。
        """

        definition = self._definitions_by_name.get(call.name)
        if definition is None:
            raise ValueError(f"tool is not available: {call.name}")
        return _declared_capsule_for_execution(
            execution=definition.execution,
            call=call,
            context=context,
            dispatcher=dispatcher,
            process_capsule_interrupt_policy=self._process_capsule_interrupt_policy,
        )


def _declared_capsule_for_execution(
    *,
    execution: ToolExecutionCapability,
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
    dispatcher: ToolDispatcher,
    process_capsule_interrupt_policy: ProcessCapsuleInterruptPolicy,
) -> ToolExecutionCapsule:
    """把声明式 execution capability 映射为 Host execution capsule。

    :param execution: 工具声明中的执行能力。
    :param call: 单次工具调用请求。
    :param context: 批式工具执行上下文。
    :param dispatcher: 当前 ToolRuntime dispatcher。
    :param process_capsule_interrupt_policy: process-backed capsule cleanup
        interrupt 策略。
    :returns: 对应的 execution capsule。
    :raises TypeError: 遇到未知 execution capability 类型时抛出。
    :raises Exception: process target factory 构造目标失败时透传。
    """

    if isinstance(execution, AsyncDirectToolExecutionCapability):
        return AsyncDirectToolExecutionCapsule(
            call=call,
            context=context,
            dispatcher=dispatcher,
        )
    if isinstance(execution, ThreadBackedToolExecutionCapability):
        return ThreadBackedToolExecutionCapsule(
            _ThreadBackedDispatchTarget(
                call=call,
                context=context,
                dispatcher=dispatcher,
            )
        )
    if isinstance(execution, ProcessBackedToolExecutionCapability):
        target = execution.target_factory.build_process_target(
            call,
            _process_backed_context_from_batch_context(context),
        )
        return ProcessBackedToolExecutionCapsule(
            target,
            interrupt_policy=process_capsule_interrupt_policy,
        )
    raise TypeError(
        f"unsupported tool execution capability: {type(execution).__name__}"
    )


def _process_backed_context_from_batch_context(
    context: BatchToolExecutionContext,
) -> ProcessBackedToolContext:
    """把批式执行上下文投影为子进程可序列化上下文。

    投影只保留 run_id、session_id、iteration_id、timeout_seconds 与
    correlation_id，不携带 cancellation_token、locks、runtime、repository、
    session 对象或 Host 内部对象。

    :param context: 批式工具执行上下文。
    :returns: process-backed 工具目标构造上下文。
    :raises Exception: 不主动抛出异常。
    """

    return ProcessBackedToolContext(
        run_id=context.run_id,
        session_id=context.session_id,
        iteration_id=context.iteration_id,
        timeout_seconds=context.timeout_seconds,
        correlation_id=context.correlation_id,
    )


class ThreadBackedToolCallable(Protocol):
    """thread-backed 测试 callable 协议。"""

    def __call__(self) -> ToolExecutionOutcome:
        """在线程中执行并返回工具 outcome。

        :returns: 工具执行 outcome。
        """

        ...


class ThreadBackedToolExecutionCapsule:
    """thread-backed 工具执行 capsule。

    该模式只能取消 wrapper awaitable，不承诺停止底层 OS thread。
    """

    def __init__(self, target: ThreadBackedToolCallable) -> None:
        """初始化 thread-backed capsule。

        :param target: 将在线程中执行的同步目标。
        :returns: ``None``。
        """

        self._target = target
        self._task: asyncio.Task[ToolExecutionOutcome] | None = None

    @property
    def mode(self) -> ToolExecutionMode:
        """返回执行模式。

        :returns: ``thread_backed``。
        """

        return ToolExecutionMode.THREAD_BACKED

    async def run(self) -> ToolExecutionOutcome:
        """在线程中运行目标。

        :returns: 工具执行 outcome。
        """

        if self._task is not None:
            raise RuntimeError("thread-backed capsule has already started")
        self._task = asyncio.create_task(asyncio.to_thread(self._target))
        return await self._task

    def request_interrupt(self, reason: str) -> None:
        """取消 wrapper task，但不声称停止 OS thread。

        :param reason: 诊断原因。
        :returns: ``None``。
        """

        del reason
        task = self._task
        if task is not None and not task.done():
            task.cancel()

    async def terminate(self, reason: str) -> ToolInterruptStepResult:
        """返回 thread terminate unsupported。

        :param reason: 诊断原因。
        :returns: unsupported terminate 结果。
        """

        del reason
        return ToolInterruptStepResult(
            supported=False,
            completed=False,
            message="thread-backed capsule cannot terminate OS thread",
        )

    async def kill(self, reason: str) -> ToolInterruptStepResult:
        """返回 thread hard kill unsupported。

        :param reason: 诊断原因。
        :returns: unsupported kill 结果。
        """

        del reason
        return ToolInterruptStepResult(
            supported=False,
            completed=False,
            message="thread-backed capsule cannot hard kill OS thread",
        )

    async def close(self) -> None:
        """释放 wrapper task。

        :returns: ``None``。
        """

        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return


class ProcessBackedToolExecutionCapsule:
    """process-backed 工具执行 capsule。"""

    def __init__(
        self,
        target: InterruptibleProcessTarget,
        *,
        interrupt_policy: ProcessCapsuleInterruptPolicy | None = None,
    ) -> None:
        """初始化 process-backed capsule。

        :param target: 可序列化子进程目标；返回值必须是工具 JSON 信封。
        :param interrupt_policy: terminate / kill cleanup grace 策略；``None``
            表示使用 Host tooling typed 默认值。
        :returns: ``None``。
        """

        self._handle = InterruptibleProcessHandle(target)
        self._interrupt_policy = (
            interrupt_policy
            if interrupt_policy is not None
            else ProcessCapsuleInterruptPolicy()
        )
        self._started = False

    @property
    def mode(self) -> ToolExecutionMode:
        """返回执行模式。

        :returns: ``process_backed``。
        """

        return ToolExecutionMode.PROCESS_BACKED

    async def run(self) -> ToolExecutionOutcome:
        """在子进程中运行目标。

        :returns: 工具执行 outcome。
        """

        if self._started:
            raise RuntimeError("process-backed capsule has already started")
        self._started = True
        self._handle.start()
        result = await self._handle.wait(timeout_seconds=None)
        if isinstance(result, InterruptibleProcessCompleted):
            return _tool_outcome_from_process_envelope(result.value)
        if isinstance(result, InterruptibleProcessFailed):
            return _tool_failed_outcome(
                error=_PROCESS_BACKED_TOOL_FAILED_ERROR,
                message=(
                    f"process-backed tool failed: {result.error_type}: "
                    f"{result.message}"
                ),
                hint=None,
            )
        if isinstance(result, InterruptibleProcessStillRunning):
            return _tool_failed_outcome(
                error=_PROCESS_BACKED_TOOL_UNEXPECTED_PENDING_ERROR,
                message="process-backed tool wait returned pending without timeout",
                hint=None,
            )
        raise TypeError("unsupported interruptible process wait result")

    def request_interrupt(self, reason: str) -> None:
        """记录 cooperative interrupt 请求。

        子进程目标不共享当前 Host cancellation token；真实中止由
        ``terminate`` / ``kill`` 执行。

        :param reason: 诊断原因。
        :returns: ``None``。
        """

        del reason

    async def terminate(self, reason: str) -> ToolInterruptStepResult:
        """terminate 子进程并等待短 cleanup grace。

        :param reason: 诊断原因。
        :returns: terminate 结果。
        """

        del reason
        result = await self._handle.terminate(
            grace_seconds=self._interrupt_policy.terminate_grace_seconds
        )
        return _tool_interrupt_result_from_process(
            result,
            success_message="process-backed capsule terminated process",
            pending_message="process-backed capsule terminate did not exit process",
        )

    async def kill(self, reason: str) -> ToolInterruptStepResult:
        """kill 子进程并等待短 cleanup grace。

        :param reason: 诊断原因。
        :returns: kill 结果。
        """

        del reason
        result = await self._handle.kill(
            grace_seconds=self._interrupt_policy.kill_grace_seconds
        )
        return _tool_interrupt_result_from_process(
            result,
            success_message="process-backed capsule killed process",
            pending_message="process-backed capsule kill did not exit process",
        )

    async def close(self) -> None:
        """关闭 process handle。

        :returns: ``None``。
        """

        await self._handle.close(
            kill_grace_seconds=self._interrupt_policy.kill_grace_seconds
        )


class DefaultToolRuntimePolicyPort:
    """默认 ToolRuntime policy port。

    本实现只覆盖 P6-S3 的 no-tool / replay 防线与 side-effect / paid
    幂等 key 必填策略；完整重复治理与等待策略由后续 slice 扩展。
    """

    def __init__(
        self,
        *,
        execution_scope: "ToolRuntimeExecutionScope",
        policy_view: ToolRuntimePolicyView,
    ) -> None:
        """初始化 policy port。

        :param execution_scope: ToolRuntime 执行范围。
        :param policy_view: Host 内部工具 policy view。
        :returns: ``None``。
        """

        self._execution_scope = execution_scope
        self._policy_view = policy_view

    def decide_tool_call(self, call: ToolCallRequest) -> ToolPolicyDecision:
        """为单次工具调用生成治理决策。

        :param call: 单次工具调用请求。
        :returns: P6-S3 工具治理决策。
        """

        if not self._execution_scope.allow_tool_calls:
            return ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
                reason_code=_TOOL_RUNTIME_NO_TOOL_REASON,
                message="tool calls are disabled for this execution scope",
            )
        rule = self._policy_view.rule_for_tool(call.name)
        if _tool_idempotency_key(call, rule) is None and (
            rule.side_effect_kind
            in (ToolSideEffectKind.SIDE_EFFECT, ToolSideEffectKind.PAID)
        ):
            return ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
                reason_code=_TOOL_RUNTIME_IDEMPOTENCY_REASON,
                message=_SIDE_EFFECT_IDEMPOTENCY_HINT,
            )
        return ToolPolicyDecision(
            kind=ToolPolicyDecisionKind.ALLOW,
            reason_code=None,
            message=None,
        )


class NoopTruncationPort:
    """P6-S3 不截断的 TruncationPort。"""

    def apply_truncation(
        self,
        tool_name: str,
        tool_call_id: str,
        outcome: ToolExecutionOutcome,
        truncate_spec: ToolTruncateSpec | None,
    ) -> TruncationAppliedOutcome:
        """原样返回工具 outcome。

        :param tool_name: 工具名。
        :param tool_call_id: 当前工具调用 id。
        :param outcome: 原始工具 outcome。
        :param truncate_spec: effective bundle 中同名工具的截断声明。
        :returns: 未截断 outcome。
        """

        del tool_name, tool_call_id, truncate_spec
        return TruncationAppliedOutcome(outcome=outcome, cursor_hint=None, fact=None)


class TruncationManager:
    """ToolRuntime 本地的 run-scoped 截断能力管理器。

    本管理器只保存当前 Run 内短生命周期 cursor，不写 durable cursor 表，
    不承诺跨进程、跨 restart、跨 recovery 或 replay 可继续补读。所有
    cursor 都是单次使用；一次 ``fetch_more`` 成功后即失效，不支持分页式
    多次补读同一个 cursor。
    """

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        attempt_id: str,
        truncate_specs_by_name: Mapping[str, ToolTruncateSpec],
    ) -> None:
        """初始化截断管理器。

        :param session_id: 当前 Session id。
        :param run_id: 当前 Run id。
        :param attempt_id: 当前 Attempt id。
        :param truncate_specs_by_name: 同一个 ``EffectiveToolBundle`` 投影出的截断声明。
        :returns: ``None``。
        """

        _require_non_empty_text(session_id, field_name="session_id")
        _require_non_empty_text(run_id, field_name="run_id")
        _require_non_empty_text(attempt_id, field_name="attempt_id")
        self._session_id = session_id
        self._run_id = run_id
        self._attempt_id = attempt_id
        self._truncate_specs_by_name = truncate_specs_by_name
        self._cursors: dict[str, ToolTruncationCursor] = {}

    def apply_truncation(
        self,
        tool_name: str,
        tool_call_id: str,
        outcome: ToolExecutionOutcome,
        truncate_spec: ToolTruncateSpec | None,
    ) -> TruncationAppliedOutcome:
        """对普通工具 completed outcome 应用截断声明。

        :param tool_name: 工具名。
        :param tool_call_id: 当前工具调用 id。
        :param outcome: 原始工具 outcome。
        :param truncate_spec: effective bundle 中同名工具的截断声明。
        :returns: 可能已截断的 outcome 与截断事实。
        """

        effective_spec = self._truncate_specs_by_name.get(tool_name)
        if effective_spec is not truncate_spec:
            truncate_spec = effective_spec
        if not isinstance(outcome, ToolCompletedOutcome):
            return TruncationAppliedOutcome(outcome=outcome, cursor_hint=None, fact=None)
        if truncate_spec is None or not truncate_spec.enabled:
            return TruncationAppliedOutcome(outcome=outcome, cursor_hint=None, fact=None)
        strategy = _tool_truncation_strategy(truncate_spec)
        if strategy is None:
            return TruncationAppliedOutcome(outcome=outcome, cursor_hint=None, fact=None)
        selected = _select_truncation_value(outcome.result.value, truncate_spec)
        if selected is None:
            return TruncationAppliedOutcome(outcome=outcome, cursor_hint=None, fact=None)
        created = _truncated_value_for_strategy(
            strategy=strategy,
            value=selected.value,
            spec=truncate_spec,
        )
        if created is None:
            return TruncationAppliedOutcome(outcome=outcome, cursor_hint=None, fact=None)
        cursor, scope_token = self._store_cursor(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            strategy=strategy,
            ttl_seconds=truncate_spec.ttl_seconds,
            remaining_ref=created.remaining_ref,
        )
        truncated_value = _replace_truncation_value(
            outcome.result.value,
            truncate_spec,
            _truncated_public_value(
                visible_value=created.visible_value,
                cursor_id=cursor.cursor_id,
                scope_token=scope_token,
            ),
        )
        if truncated_value is None:
            self._cursors.pop(cursor.cursor_id, None)
            return TruncationAppliedOutcome(
                outcome=_truncation_failure(
                    "tool result target cannot be replaced safely",
                ),
                cursor_hint=None,
                fact=None,
            )
        truncated_outcome = ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=truncated_value,
                meta=outcome.result.meta,
            )
        )
        fact = ToolTruncationFact(
            applied=True,
            strategy=strategy.value,
            original_digest=_tool_outcome_digest(outcome),
            truncated_digest=_tool_outcome_digest(truncated_outcome),
            cursor_hint=cursor.cursor_id,
        )
        return TruncationAppliedOutcome(
            outcome=truncated_outcome,
            cursor_hint=cursor.cursor_id,
            fact=fact,
        )

    def fetch_more(
        self,
        request: FetchMoreRequest,
        context: BatchToolExecutionContext,
    ) -> FetchMoreResult:
        """按 cursor 补读剩余内容。

        :param request: ``fetch_more`` 请求。
        :param context: 批式工具执行上下文。
        :returns: 普通 completed 或 failed 工具 outcome。
        """

        cursor = self._cursors.get(request.cursor)
        if cursor is None:
            self._cleanup_expired_cursors(datetime.now(UTC))
            return _truncation_failure(
                "truncation cursor is missing or no longer available",
            )
        validation_failure = self._validate_cursor(cursor, request, context)
        if validation_failure is not None:
            if datetime.now(UTC) > cursor.expires_at:
                self._cursors.pop(cursor.cursor_id, None)
            self._cleanup_expired_cursors(datetime.now(UTC))
            return validation_failure
        fetched = _fetch_more_value(cursor.remaining_ref, request.limit)
        if fetched is None:
            self._cleanup_expired_cursors(datetime.now(UTC))
            return _truncation_failure(
                "truncation remainder digest mismatch",
            )
        fetched_outcome = ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value=fetched, meta=None)
        )
        if cursor.single_use:
            self._cursors.pop(cursor.cursor_id, None)
        self._cleanup_expired_cursors(datetime.now(UTC))
        return fetched_outcome

    def _store_cursor(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        strategy: ToolTruncationStrategy,
        ttl_seconds: int | None,
        remaining_ref: TruncatedRemainderRef,
    ) -> tuple[ToolTruncationCursor, str]:
        """保存 run-local cursor。

        :param tool_name: 工具名。
        :param tool_call_id: 工具调用 id。
        :param strategy: 截断策略。
        :param ttl_seconds: cursor TTL；无则使用默认值。
        :param remaining_ref: 剩余内容引用。
        :returns: cursor 与明文 scope token。
        """

        now = datetime.now(UTC)
        self._cleanup_expired_cursors(now)
        ttl = ttl_seconds if ttl_seconds is not None else _DEFAULT_TRUNCATION_TTL_SECONDS
        scope_token = secrets.token_urlsafe(32)
        cursor_id = f"trunc-{secrets.token_urlsafe(24)}"
        cursor = ToolTruncationCursor(
            cursor_id=cursor_id,
            scope_token_digest=_scope_token_digest(scope_token),
            session_id=self._session_id,
            run_id=self._run_id,
            attempt_id=self._attempt_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            strategy=strategy,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            remaining_ref=remaining_ref,
            single_use=True,
            used_at=None,
        )
        self._cursors[cursor.cursor_id] = cursor
        return cursor, scope_token

    def _cleanup_expired_cursors(self, now: datetime) -> None:
        """有界清理已过期 cursor。

        :param now: 当前 UTC 时间。
        :returns: ``None``。
        """

        scanned_count = 0
        expired_cursor_ids: list[str] = []
        for cursor_id, cursor in self._cursors.items():
            if (
                scanned_count >= _TRUNCATION_EXPIRED_CLEANUP_SCAN_LIMIT
                or len(expired_cursor_ids) >= _TRUNCATION_EXPIRED_CLEANUP_LIMIT
            ):
                break
            scanned_count += 1
            if now > cursor.expires_at:
                expired_cursor_ids.append(cursor_id)
        for cursor_id in expired_cursor_ids:
            self._cursors.pop(cursor_id, None)

    def _validate_cursor(
        self,
        cursor: ToolTruncationCursor,
        request: FetchMoreRequest,
        context: BatchToolExecutionContext,
    ) -> ToolFailedOutcome | None:
        """校验 cursor 的 run scope、token、TTL、single-use 与剩余摘要。

        :param cursor: 已查到的 cursor。
        :param request: ``fetch_more`` 请求。
        :param context: 批式工具上下文。
        :returns: 校验失败 outcome；通过时为 ``None``。
        """

        if (
            cursor.session_id != self._session_id
            or cursor.run_id != self._run_id
            or cursor.attempt_id != self._attempt_id
            or context.session_id != self._session_id
            or context.run_id != self._run_id
        ):
            return _truncation_failure(
                "truncation cursor does not belong to this run scope",
            )
        if cursor.scope_token_digest != _scope_token_digest(request.scope_token):
            return _truncation_failure(
                "truncation scope token does not match cursor",
            )
        if datetime.now(UTC) > cursor.expires_at:
            return _truncation_failure(
                "truncation cursor expired",
            )
        if cursor.single_use and cursor.used_at is not None:
            return _truncation_failure(
                "truncation cursor has already been used",
            )
        if not _remainder_digest_matches(cursor.remaining_ref):
            return _truncation_failure(
                "truncation remainder digest mismatch",
            )
        return None


class FetchMoreToolCallable:
    """作为普通 framework tool 注入的 ``fetch_more`` callable。"""

    def __init__(self) -> None:
        """初始化尚未绑定 manager 的 callable。

        :returns: ``None``。
        """

        self._manager: TruncationManager | None = None

    def bind_manager(self, manager: TruncationManager) -> None:
        """绑定同一 effective bundle 派生的截断管理器。

        :param manager: 当前 ToolRuntime 的截断管理器。
        :returns: ``None``。
        """

        self._manager = manager

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行普通 ``fetch_more`` 工具调用。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 普通 completed 或 failed outcome。
        """

        if self._manager is None:
            return _truncation_failure(
                "truncation manager is not enabled for this run",
            )
        request = _fetch_more_request_from_call(call)
        if isinstance(request, ToolFailedOutcome):
            return request
        return self._manager.fetch_more(request, context)


class DeterministicToolTraceDiagnosticEmitter:
    """不落盘的确定性 ToolRuntime 诊断引用发射器。"""

    def emit(self, record: ToolTraceDiagnosticRecord) -> ToolTraceDiagnosticRef:
        """发出确定性诊断引用。

        :param record: 诊断记录。
        :returns: 由诊断内容 digest 派生的引用。
        """

        _require_non_empty_text(record.reason_code, field_name="reason_code")
        _require_non_empty_text(record.message, field_name="message")
        ref_digest = sha256_digest_json(
            {
                "reason_code": record.reason_code,
                "message": record.message,
            }
        ).removeprefix("sha256:")
        return ToolTraceDiagnosticRef(ref_id=f"tool-diagnostic-{ref_digest}")


class NoopToolTraceDiagnosticEmitter:
    """不保存诊断内容的 ToolRuntime 诊断发射器。"""

    def emit(self, record: ToolTraceDiagnosticRecord) -> ToolTraceDiagnosticRef:
        """忽略诊断内容并返回固定引用。

        :param record: 诊断记录。
        :returns: 固定 no-op 诊断引用。
        :raises ValueError: 诊断字段为空时抛出。
        """

        _require_non_empty_text(record.reason_code, field_name="reason_code")
        _require_non_empty_text(record.message, field_name="message")
        return ToolTraceDiagnosticRef(ref_id=_TOOL_RUNTIME_DIAGNOSTIC_NOOP_REF)


class InMemoryToolTraceDiagnosticEmitter:
    """测试用内存态 ToolRuntime 诊断发射器。"""

    def __init__(self) -> None:
        """初始化内存诊断发射器。

        :returns: ``None``。
        """

        self._records: list[ToolTraceDiagnosticRecord] = []

    @property
    def records(self) -> tuple[ToolTraceDiagnosticRecord, ...]:
        """返回已发出的诊断记录。

        :returns: 按发出顺序排列的诊断记录。
        """

        return tuple(self._records)

    def emit(self, record: ToolTraceDiagnosticRecord) -> ToolTraceDiagnosticRef:
        """保存诊断记录并返回内存引用。

        :param record: 诊断记录。
        :returns: 指向内存序号的诊断引用。
        :raises ValueError: 诊断字段为空时抛出。
        """

        _require_non_empty_text(record.reason_code, field_name="reason_code")
        _require_non_empty_text(record.message, field_name="message")
        self._records.append(record)
        return ToolTraceDiagnosticRef(
            ref_id=f"tool-diagnostic-memory-{len(self._records)}"
        )


class DefaultHostToolFactAcceptPort:
    """基于 Host durable store 的工具事实 accept barrier 实现。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore | None = None,
        idempotency_store: IdempotencyStore | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
    ) -> None:
        """初始化默认 accept port。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog primitive；无则创建默认实现。
        :param idempotency_store: Idempotency primitive；无则创建默认实现。
        :param projection_catchup_port: commit 后 best-effort projection catch-up 端口。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = (
            event_log_store if event_log_store is not None else EventLogStore()
        )
        self._idempotency_store = (
            idempotency_store
            if idempotency_store is not None
            else IdempotencyStore()
        )
        self._projection_catchup_port = projection_catchup_port

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """接受工具事实候选并写入 canonical EventLog facts。

        :param candidate: 工具事实候选。
        :returns: accepted ack、rejected ack 或 timeout 结果。
        """

        try:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                (
                    "host.tool_runtime.accept_tool_fact.accepted "
                    "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
                    "tool_call_id=%s tool_name=%s tool_fact_kind=%s"
                ),
                candidate.identity.session_id,
                candidate.identity.run_id,
                candidate.identity.attempt_id,
                candidate.identity.execution_id,
                candidate.call.tool_call_id,
                candidate.call.tool_name,
                candidate.tool_fact_kind.value,
            )
            result = self._transaction_runner.run_write(
                lambda transaction: self._accept_in_transaction(
                    transaction, candidate
                )
            )
            _log_tool_fact_accept_result(candidate, result)
            if (
                isinstance(result, ToolFactAcceptedAck)
                and result.tool_result_event_ref is not None
            ):
                catch_up_projection_best_effort(self._projection_catchup_port)
            return result
        except HostIdempotencyConflictError:
            result = _rejected_ack(
                candidate,
                ToolAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                "tool fact accept idempotency conflict",
                retryable=False,
            )
            _log_tool_fact_accept_result(candidate, result)
            return result
        except HostPayloadReferenceError:
            result = _rejected_ack(
                candidate,
                ToolAcceptRejectReason.PAYLOAD_REFERENCE_INVALID,
                "tool fact payload reference is invalid",
                retryable=False,
            )
            _log_tool_fact_accept_result(candidate, result)
            return result

    def _accept_in_transaction(
        self, transaction: HostTransaction, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """在单个 Host write transaction 内执行 accept。

        :param transaction: 当前 Host transaction。
        :param candidate: 工具事实候选。
        :returns: accept 结果。
        """

        scope = _accept_idempotency_scope(candidate)
        existing = self._idempotency_store.read_idempotency_record(
            transaction, scope
        )
        if existing is not None:
            if (
                existing.semantic_input_digest
                != candidate.idempotency.semantic_input_digest
            ):
                return _rejected_ack(
                    candidate,
                    ToolAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                    "tool fact accept idempotency conflict",
                    retryable=False,
                )
            return _accepted_ack_from_existing(
                self._event_log_store, transaction, candidate, existing
            )

        context = _read_accept_context(transaction, candidate)
        invalid_reason = _invalid_accept_context_reason(context, candidate)
        if invalid_reason is not None:
            return _rejected_ack(
                candidate,
                invalid_reason,
                "tool fact accept precondition failed",
                retryable=False,
            )
        if not _candidate_payload_descriptor_exists(transaction, candidate):
            return _rejected_ack(
                candidate,
                ToolAcceptRejectReason.PAYLOAD_REFERENCE_INVALID,
                "tool fact payload descriptor is missing",
                retryable=False,
            )

        event_plan = _tool_accept_event_plan(candidate)
        occurred_at = datetime.now(UTC)
        requested = self._event_log_store.append_event(
            transaction,
            build_tool_call_requested_event_request(
                transaction,
                atom=_tool_call_request_atom(candidate),
                event_id=event_plan.requested_id,
                occurred_at=occurred_at,
                origin=ToolCallRequestEventOrigin.ORDINARY_ACCEPT,
            ),
        ).row
        governed = _append_tool_call_governed_if_needed(
            self._event_log_store,
            transaction,
            candidate,
            event_plan.governed_id,
            requested,
        )
        result = _append_tool_result_if_needed(
            self._event_log_store,
            transaction,
            candidate,
            event_plan.result_id,
            requested,
            governed,
        )
        created_event = _created_event_for_idempotency(requested, governed, result)
        record = self._idempotency_store.record_idempotent_result(
            transaction,
            scope,
            candidate.idempotency.semantic_input_digest,
            IdempotencyResultRef(
                result_kind=_TOOL_FACT_ACCEPT_RESULT_KIND,
                result_ref=event_plan.tool_fact_id,
                created_event_id=created_event.event_id,
                created_event_sequence=created_event.event_sequence,
            ),
        )
        return _accepted_ack_from_rows(
            candidate=candidate,
            tool_fact_id=event_plan.tool_fact_id,
            requested=requested,
            governed=governed,
            result=result,
            idempotency_record=record,
        )


@dataclass(frozen=True, slots=True)
class _FrameworkInjectionContext:
    """framework tool 注入结果。

    :param definitions: 实际注入的工具声明。
    :param fetch_more_callable: ``fetch_more`` callable；未注入时为 ``None``。
    """

    definitions: tuple[ToolDefinition, ...]
    fetch_more_callable: FetchMoreToolCallable | None


@dataclass(frozen=True, slots=True)
class EffectiveToolBundle:
    """Attempt-local effective 工具集合。

    :param business_bundle: 外部装配传入的业务工具集合。
    :param definitions_by_name: effective 工具声明映射。
    :param tool_schemas: 从同一 effective bundle 投影出的 Engine schema。
    :param truncate_specs_by_name: 从同一 effective bundle 投影出的截断声明。
    :param source_refs: 业务工具来源引用。
    :param enabled_framework_tools: policy view 中启用的 framework tool 集合。
    :param injected_framework_tool_names: 本次实际注入的 framework tool 名称。
    :param business_bundle_digest: 业务 bundle 诊断摘要。
    :param effective_schema_digest: effective schema 诊断摘要。
    :param policy_snapshot_digest: policy snapshot 摘要；无时为 ``None``。
    :param fetch_more_callable: 注入的 ``fetch_more`` callable；未注入时为 ``None``。
    """

    business_bundle: ToolBundle
    definitions_by_name: Mapping[str, ToolDefinition]
    tool_schemas: tuple[ToolSchema, ...]
    truncate_specs_by_name: Mapping[str, ToolTruncateSpec]
    source_refs: tuple[ToolBundleSourceRef, ...]
    enabled_framework_tools: frozenset[FrameworkToolName]
    injected_framework_tool_names: frozenset[FrameworkToolName]
    business_bundle_digest: str
    effective_schema_digest: str
    policy_snapshot_digest: str | None
    fetch_more_callable: FetchMoreToolCallable | None


@dataclass(frozen=True, slots=True)
class EffectiveToolBundleBuildRequest:
    """EffectiveToolBundleBuilder 的输入。

    :param business_tool_bundle: 外部装配好的业务工具集合。
    :param selected_business_tool_names: 本次 Run 选择的业务工具名；
        ``None`` 表示使用全部业务工具，空集合表示不启用业务工具。
    :param source_refs: 业务工具来源引用。
    :param framework_tool_policy: framework tool policy view。
    :param policy_snapshot_digest: policy snapshot 摘要；无时为 ``None``。
    :param enable_truncation_manager: 是否启用 run-scoped truncation manager。
    """

    business_tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    framework_tool_policy: FrameworkToolPolicyView
    policy_snapshot_digest: str | None
    selected_business_tool_names: frozenset[str] | None = None
    enable_truncation_manager: bool = False


class EffectiveToolBundleBuilder:
    """构造 attempt-local effective 工具集合。"""

    def __init__(
        self, framework_injector: FrameworkToolInjector | None = None
    ) -> None:
        """初始化 builder。

        :param framework_injector: 可选 framework tool 注入 hook；无 hook 时不注入。
        :returns: ``None``。
        """

        self._framework_injector = framework_injector

    def build(
        self, request: EffectiveToolBundleBuildRequest
    ) -> EffectiveToolBundle:
        """从业务 bundle 与 framework policy 构造 effective bundle。

        :param request: effective bundle 构造输入。
        :returns: attempt-local effective bundle。
        :raises ValueError: 来源引用为空、业务工具占用预留名或注入结果非法时抛出。
        """

        if not request.source_refs:
            raise ValueError("EffectiveToolBundle.source_refs must be non-empty")
        _validate_reserved_name_conflicts(
            request.business_tool_bundle,
            request.framework_tool_policy,
        )
        definitions = list(
            _selected_business_definitions(
                request.business_tool_bundle,
                request.selected_business_tool_names,
            )
        )
        injected_context = self._inject_framework_definitions(
            request.framework_tool_policy,
            enable_truncation_manager=request.enable_truncation_manager,
        )
        injected = injected_context.definitions
        definitions.extend(injected)
        definitions_by_name = _definitions_by_name(definitions)
        tool_schemas = tuple(
            definition.to_tool_schema() for definition in definitions
        )
        truncate_specs = {
            definition.name: effective_tool_truncate_spec(
                definition.truncate,
                default_limits_by_strategy=(
                    _DEFAULT_TRUNCATION_LIMITS_BY_STRATEGY
                ),
                default_ttl_seconds=_DEFAULT_TRUNCATION_TTL_SECONDS,
            )
            for definition in definitions
            if definition.truncate is not None
        }
        return EffectiveToolBundle(
            business_bundle=request.business_tool_bundle,
            definitions_by_name=MappingProxyType(definitions_by_name),
            tool_schemas=tool_schemas,
            truncate_specs_by_name=MappingProxyType(truncate_specs),
            source_refs=request.source_refs,
            enabled_framework_tools=request.framework_tool_policy.enabled_framework_tools,
            injected_framework_tool_names=frozenset(
                FrameworkToolName(definition.name) for definition in injected
            ),
            business_bundle_digest=_business_bundle_digest(
                request.business_tool_bundle
            ),
            effective_schema_digest=_tool_schemas_digest(tool_schemas),
            policy_snapshot_digest=request.policy_snapshot_digest,
            fetch_more_callable=injected_context.fetch_more_callable,
        )

    def _inject_framework_definitions(
        self,
        policy: FrameworkToolPolicyView,
        *,
        enable_truncation_manager: bool,
    ) -> "_FrameworkInjectionContext":
        """按 policy 通过 hook 注入 framework tool。

        :param policy: framework tool policy view。
        :param enable_truncation_manager: truncation manager 是否启用。
        :returns: framework 注入上下文。
        :raises ValueError: hook 返回的工具名与请求名称不一致时抛出。
        """

        fetch_more_callable: FetchMoreToolCallable | None = None
        definitions: list[ToolDefinition] = []
        for tool_name in sorted(
            policy.enabled_framework_tools, key=lambda item: item.value
        ):
            if (
                tool_name is FrameworkToolName.FETCH_MORE
                and enable_truncation_manager
            ):
                fetch_more_callable = FetchMoreToolCallable()
                definition = _fetch_more_tool_definition(fetch_more_callable)
            elif self._framework_injector is not None:
                definition = self._framework_injector.build_framework_tool(tool_name)
            else:
                continue
            if definition.name != tool_name.value:
                raise ValueError(
                    "framework injector returned mismatched tool name:"
                    f" {definition.name}"
                )
            definitions.append(definition)
        return _FrameworkInjectionContext(
            definitions=tuple(definitions),
            fetch_more_callable=fetch_more_callable,
        )


def _selected_business_definitions(
    bundle: ToolBundle, selected_tool_names: frozenset[str] | None
) -> tuple[ToolDefinition, ...]:
    """按 per-run selector 过滤业务工具声明。

    :param bundle: construction-time 全量业务工具集合。
    :param selected_tool_names: per-run 业务工具名选择器；``None`` 表示全量。
    :returns: 本次 Run 有效业务工具声明。
    :raises ValueError: selector 包含未知业务工具名时抛出。
    """

    if selected_tool_names is None:
        return bundle.definitions
    known_names = frozenset(definition.name for definition in bundle.definitions)
    unknown = selected_tool_names.difference(known_names)
    if unknown:
        raise ValueError(
            "selected business tool names are unknown: " + ",".join(sorted(unknown))
        )
    return tuple(
        definition
        for definition in bundle.definitions
        if definition.name in selected_tool_names
    )


@dataclass(frozen=True, slots=True)
class ToolRuntimeBuildRequest:
    """ToolRuntime factory 构造输入。

    :param effective_bundle_request: effective bundle 构造输入。
    :param execution_scope: 执行期 attempt identity；无则只构造未连接 executor。
    :param accept_port: Host accept barrier；无则只构造未连接 executor。
    :param awaiting_accept_port: Host awaiting accept barrier；无则 awaiting
        outcome 返回受治理错误。
    :param wait_adapter_registry: Host 等待 adapter registry；无则 awaiting
        outcome 返回受治理错误。
    :param wait_activation_registry: Host accepted wait activation registry；无则
        accepted wait 不执行 activation。
    :param retry_policy: accept ack 有限重试策略。
    :param policy_view: Host 内部工具 policy view。
    :param duplicate_governance_policy: ToolRuntime 使用的 duplicate governance
        策略。
    :param process_capsule_interrupt_policy: process-backed capsule terminate /
        kill cleanup grace 策略。
    :param diagnostic_emitter: 诊断 emitter；无则使用确定性内存引用实现。
    :param execution_capsule_factory: 测试用内部 execution capsule factory
        override；无则按 effective ``ToolDefinition.execution`` 创建 capsule。
    """

    effective_bundle_request: EffectiveToolBundleBuildRequest
    execution_scope: ToolRuntimeExecutionScope | None = None
    accept_port: HostToolFactAcceptPort | None = None
    awaiting_accept_port: HostToolAwaitingAcceptPort | None = None
    wait_adapter_registry: WaitAdapterRegistry | None = None
    wait_activation_registry: WaitActivationRegistry | None = None
    retry_policy: ToolAcceptRetryPolicy = field(
        default_factory=_default_tool_accept_retry_policy
    )
    policy_view: ToolRuntimePolicyView = field(
        default_factory=ToolRuntimePolicyView
    )
    duplicate_governance_policy: DuplicateGovernancePolicy = field(
        default_factory=DuplicateGovernancePolicy
    )
    process_capsule_interrupt_policy: ProcessCapsuleInterruptPolicy = field(
        default_factory=ProcessCapsuleInterruptPolicy
    )
    diagnostic_emitter: ToolTraceDiagnosticEmitter | None = None
    execution_capsule_factory: ToolExecutionCapsuleFactory | None = None


@dataclass(frozen=True, slots=True)
class ToolRuntimeUnsupportedExecutor:
    """P6-S1 明确不执行真实工具的 ToolExecutor stub。

    :param effective_bundle: 与 schema provider 同源的 effective bundle。
    """

    effective_bundle: EffectiveToolBundle

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回与输入双射的 unsupported tool failure。

        :param request: 批式工具执行请求。
        :returns: 每个 call 对应一条 unsupported failure record。
        """

        return BatchToolExecutionOutcome(
            records=tuple(
                BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=ToolFailedOutcome(
                        result=ToolResultFailure(
                            ok=False,
                            error=_UNSUPPORTED_EXECUTOR_ERROR,
                            message=_UNSUPPORTED_EXECUTOR_MESSAGE,
                            hint=None,
                            meta=None,
                        )
                    ),
                )
                for call in request.calls
            )
        )


class ToolRuntimeExecutor:
    """Host-governed ToolExecutor 实现。

    本 executor 是 Engine 与 Host ToolRuntime 的唯一工具执行桥：业务
    callable 的结果必须先经 Host accept barrier accepted，才会返回给
    Engine；rejected ack、timeout、policy rejection 与 awaiting 均只返回
    受治理的工具错误。
    """

    def __init__(
        self,
        *,
        effective_bundle: EffectiveToolBundle,
        execution_scope: ToolRuntimeExecutionScope,
        dispatcher: ToolDispatcher,
        policy_port: ToolRuntimePolicyPort,
        duplicate_governance: DuplicateGovernancePort,
        truncation_port: TruncationPort,
        accept_port: HostToolFactAcceptPort,
        awaiting_accept_port: HostToolAwaitingAcceptPort | None,
        wait_adapter_registry: WaitAdapterRegistry | None,
        wait_activation_registry: WaitActivationRegistry | None,
        retry_policy: ToolAcceptRetryPolicy,
        policy_view: ToolRuntimePolicyView,
        diagnostic_emitter: ToolTraceDiagnosticEmitter,
        execution_capsule_factory: ToolExecutionCapsuleFactory,
    ) -> None:
        """初始化 ToolRuntimeExecutor。

        :param effective_bundle: attempt-local effective bundle。
        :param execution_scope: ToolRuntime 执行范围。
        :param dispatcher: 单工具 dispatcher。
        :param policy_port: 工具治理决策端口。
        :param duplicate_governance: duplicate governance 端口。
        :param truncation_port: 截断端口。
        :param accept_port: Host accept barrier。
        :param awaiting_accept_port: Host awaiting accept barrier。
        :param wait_adapter_registry: Host 等待 adapter registry。
        :param wait_activation_registry: Host accepted wait activation registry。
        :param retry_policy: accept ack 有限重试策略。
        :param policy_view: Host 内部工具 policy view。
        :param diagnostic_emitter: 诊断 emitter。
        :param execution_capsule_factory: 单工具执行 capsule factory。
        :returns: ``None``。
        """

        self._effective_bundle = effective_bundle
        self._execution_scope = execution_scope
        self._dispatcher = dispatcher
        self._policy_port = policy_port
        self._duplicate_governance = duplicate_governance
        self._truncation_port = truncation_port
        self._accept_port = accept_port
        self._awaiting_accept_port = awaiting_accept_port
        self._wait_adapter_registry = wait_adapter_registry
        self._wait_activation_registry = wait_activation_registry
        self._retry_policy = retry_policy
        self._policy_view = policy_view
        self._diagnostic_emitter = diagnostic_emitter
        self._execution_capsule_factory = execution_capsule_factory

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """执行批式工具调用并等待 Host accepted ack。

        :param request: Engine 发起的批式工具执行请求。
        :returns: 与输入 calls 严格双射的批式工具 outcome。
        """

        records: list[BatchToolExecutionRecord] = []
        batch_deadline = _batch_timeout_deadline(request.context.timeout_seconds)
        run_suspended_by_awaiting = False
        for call in request.calls:
            if run_suspended_by_awaiting:
                records.append(
                    BatchToolExecutionRecord(
                        tool_call_id=call.tool_call_id,
                        outcome=_governed_failure_outcome(
                            ToolPolicyDecision(
                                kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
                                reason_code=(
                                    _TOOL_RUNTIME_AWAITING_BATCH_SUSPENDED_REASON
                                ),
                                message=(
                                    "tool batch stopped after awaiting suspension"
                                ),
                            )
                        ),
                    )
                )
                continue
            record = await self._execute_one(call, request.context, batch_deadline)
            records.append(record)
            if isinstance(record.outcome, ToolAwaitingOutcome):
                run_suspended_by_awaiting = True
        return BatchToolExecutionOutcome(records=tuple(records))

    async def _execute_one(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        batch_deadline: float | None,
    ) -> BatchToolExecutionRecord:
        """执行单次工具调用。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param batch_deadline: 批级 timeout 单调时钟 deadline；无 timeout 时为 ``None``。
        :returns: 单次工具调用记录。
        """

        normalized_arguments_digest = _normalized_arguments_digest(call)
        schema_digest = _tool_schema_digest_for_call(self._effective_bundle, call)
        identity_digest = _tool_identity_digest(
            effective_bundle=self._effective_bundle,
            tool_name=call.name,
            schema_digest=schema_digest,
        )
        tool_policy = self._policy_view.rule_for_tool(call.name)
        duplicate_request = DuplicateGovernanceRequest(
            scope=DuplicateGovernanceScope(
                kind="attempt",
                attempt_id=self._execution_scope.attempt_id,
            ),
            tool_name=call.name,
            tool_identity_digest=identity_digest,
            normalized_arguments_digest=normalized_arguments_digest,
            arguments=call.arguments,
            semantic_duplicate_key=_semantic_duplicate_key(call, tool_policy),
        )
        duplicate_decision = await self._duplicate_governance.decide_duplicate(
            duplicate_request
        )
        duplicate_owner_needs_terminal = (
            duplicate_decision.kind is DuplicateDecisionKind.ALLOW
            and not duplicate_decision.prior_event_refs
        )
        duplicate_terminal_recorded = False
        durable_missing_reason = DuplicateDurableMissingReason.GOVERNED_BEFORE_ACCEPT
        policy_decision = self._policy_port.decide_tool_call(call)
        try:
            if not _request_context_matches_scope(context, self._execution_scope):
                policy_decision = ToolPolicyDecision(
                    kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
                    reason_code=_TOOL_RUNTIME_NO_TOOL_REASON,
                    message="tool request context does not match execution scope",
                )
            duplicate_refs = self._diagnostic_refs_for_duplicate(duplicate_decision)
            if duplicate_decision.kind is DuplicateDecisionKind.AWAITING_FANOUT:
                return self._awaiting_fanout_record(
                    call=call,
                    duplicate_decision=duplicate_decision,
                )
            duplicate_governed = False
            if (
                policy_decision.kind is ToolPolicyDecisionKind.ALLOW
                and duplicate_decision.kind is not DuplicateDecisionKind.ALLOW
            ):
                duplicate_governed = True
                policy_decision = _policy_decision_from_duplicate(duplicate_decision)
            if policy_decision.kind is ToolPolicyDecisionKind.REUSE:
                return await self._accept_reuse(
                    call=call,
                    context=context,
                    normalized_arguments_digest=normalized_arguments_digest,
                    duplicate_decision=duplicate_decision,
                    policy_decision=policy_decision,
                    tool_idempotency_key=_tool_idempotency_key(call, tool_policy),
                    diagnostic_refs=duplicate_refs,
                )
            if duplicate_decision.kind is DuplicateDecisionKind.DURABLE_MISSING:
                return BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=_governed_failure_outcome(policy_decision),
                )
            if policy_decision.kind is not ToolPolicyDecisionKind.ALLOW:
                outcome = _governed_failure_outcome(policy_decision)
            else:
                raw_outcome, bounded_policy_decision = await (
                    self._dispatch_tool_call_with_bounds(call, context, batch_deadline)
                )
                if bounded_policy_decision is not None:
                    policy_decision = bounded_policy_decision
                    durable_missing_reason = _durable_missing_reason_for_policy(
                        policy_decision
                    )
                if _is_runtime_dispatch_exception_outcome(raw_outcome):
                    durable_missing_reason = DuplicateDurableMissingReason.TOOL_EXCEPTION
                    return BatchToolExecutionRecord(
                        tool_call_id=call.tool_call_id,
                        outcome=raw_outcome,
                    )
                if isinstance(raw_outcome, ToolAwaitingOutcome):
                    awaiting_result = await self._accept_awaiting(
                        call=call,
                        context=context,
                        normalized_arguments_digest=normalized_arguments_digest,
                        schema_digest=schema_digest,
                        identity_digest=identity_digest,
                        awaiting_outcome=raw_outcome,
                        duplicate_request=duplicate_request,
                        duplicate_decision=duplicate_decision,
                        policy_decision=policy_decision,
                        diagnostic_refs=duplicate_refs,
                    )
                    duplicate_terminal_recorded = (
                        awaiting_result.duplicate_terminal_recorded
                    )
                    if awaiting_result.durable_missing_reason is not None:
                        durable_missing_reason = (
                            awaiting_result.durable_missing_reason
                        )
                    return awaiting_result.record
                outcome, policy_decision = self._normalize_runtime_outcome(
                    raw_outcome, policy_decision
                )
            truncation = self._truncation_port.apply_truncation(
                call.name,
                call.tool_call_id,
                outcome,
                self._effective_bundle.truncate_specs_by_name.get(call.name),
            )
            accepted_outcome = truncation.outcome
            bounded_result = self._observe_llm_inline_tool_result(
                call=call,
                outcome=accepted_outcome,
                policy_decision=policy_decision,
                truncation_fact=truncation.fact,
            )
            accepted_outcome = bounded_result.outcome
            policy_decision = bounded_result.policy_decision
            diagnostic_refs = (*duplicate_refs, *bounded_result.diagnostic_refs)
            candidate = _tool_fact_accept_candidate(
                scope=self._execution_scope,
                effective_bundle=self._effective_bundle,
                call=call,
                iteration_id=context.iteration_id,
                normalized_arguments_digest=normalized_arguments_digest,
                outcome=accepted_outcome,
                truncation_fact=truncation.fact,
                policy_decision=policy_decision,
                duplicate_decision=duplicate_decision,
                duplicate_governed=duplicate_governed,
                tool_idempotency_key=_tool_idempotency_key(call, tool_policy),
                diagnostic_refs=diagnostic_refs,
            )
            accept_result = await self._accept_with_retry(candidate)
            if isinstance(accept_result, ToolFactAcceptedAck):
                duplicate_terminal_recorded = await self._record_duplicate_accepted(
                    duplicate_request=duplicate_request,
                    accepted_ack=accept_result,
                    accepted_outcome=accepted_outcome,
                    duplicate_decision=duplicate_decision,
                    policy_decision=policy_decision,
                )
                return BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=accepted_outcome,
                )
            durable_missing_reason = _durable_missing_reason_for_accept_result(
                accept_result
            )
            governed = _accept_failure_outcome(accept_result)
            return BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=governed,
            )
        finally:
            if duplicate_owner_needs_terminal and not duplicate_terminal_recorded:
                await self._record_duplicate_durable_missing_best_effort(
                    duplicate_request,
                    durable_missing_reason,
                )

    async def _record_duplicate_durable_missing_best_effort(
        self,
        duplicate_request: DuplicateGovernanceRequest,
        durable_missing_reason: DuplicateDurableMissingReason,
    ) -> None:
        """best-effort 记录 duplicate owner 未产出 durable fact。

        cleanup 只用于释放同 Attempt 内等待相同 duplicate key 的调用者，不能
        覆盖工具执行、accept barrier 或 return path 的原始结果。

        :param duplicate_request: duplicate governance 查询输入。
        :param durable_missing_reason: owner 未产出 durable fact 的原因。
        :returns: ``None``。
        :raises: 不向调用方传播 cleanup 或诊断失败。
        """

        try:
            await self._duplicate_governance.record_durable_missing(
                duplicate_request,
                durable_missing_reason,
            )
        except Exception as exc:
            _LOGGER.warning(
                "host.tool_runtime.duplicate_cleanup_failed "
                "session_id=%s run_id=%s attempt_id=%s tool_name=%s "
                "error_type=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                duplicate_request.tool_name,
                exc.__class__.__name__,
                exc_info=True,
            )
            self._emit_duplicate_cleanup_diagnostic_best_effort(exc)

    def _emit_duplicate_cleanup_diagnostic_best_effort(self, exc: Exception) -> None:
        """best-effort 发出 duplicate cleanup 失败诊断。

        :param exc: cleanup 抛出的异常。
        :returns: ``None``。
        :raises: 不向调用方传播诊断失败。
        """

        try:
            self._diagnostic_emitter.emit(
                ToolTraceDiagnosticRecord(
                    reason_code=_TOOL_RUNTIME_DUPLICATE_CLEANUP_FAILURE_REASON,
                    message=(
                        "duplicate durable-missing cleanup failed: "
                        f"{exc.__class__.__name__}"
                    ),
                )
            )
        except Exception:
            _LOGGER.warning(
                "host.tool_runtime.duplicate_cleanup_diagnostic_failed "
                "session_id=%s run_id=%s attempt_id=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                exc_info=True,
            )

    def _observe_llm_inline_tool_result(
        self,
        *,
        call: ToolCallRequest,
        outcome: ToolExecutionOutcome,
        policy_decision: ToolPolicyDecision,
        truncation_fact: ToolTruncationFact | None,
    ) -> "_InlineToolResultGovernance":
        """记录 LLM-facing 工具结果大小摘要，不执行默认 inline 治理。

        :param call: 当前工具调用。
        :param outcome: 准备进入 accept barrier 并返回给 Engine 的工具 outcome。
        :param policy_decision: 当前工具治理决策。
        :param truncation_fact: 显式截断产生的事实；未截断时为 ``None``。
        :returns: 原样 outcome、policy decision 与空诊断引用。
        """

        size_bytes = _tool_outcome_inline_size_bytes(outcome)
        if truncation_fact is not None and truncation_fact.applied:
            _LOGGER.debug(
                "host.tool_runtime.truncation_applied session_id=%s "
                "run_id=%s attempt_id=%s tool_name=%s tool_call_id=%s "
                "strategy=%s outcome_size_bytes=%s cursor_hint_present=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                call.name,
                call.tool_call_id,
                truncation_fact.strategy,
                size_bytes,
                truncation_fact.cursor_hint is not None,
            )
        elif (
            isinstance(outcome, ToolCompletedOutcome)
            and size_bytes > _TOOL_RESULT_SIZE_LOG_THRESHOLD_BYTES
        ):
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.tool_runtime.large_tool_result_passthrough session_id=%s "
                "run_id=%s attempt_id=%s tool_name=%s tool_call_id=%s "
                "outcome_size_bytes=%s truncate_spec_present=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                call.name,
                call.tool_call_id,
                size_bytes,
                call.name in self._effective_bundle.truncate_specs_by_name,
            )
        return _InlineToolResultGovernance(
            outcome=outcome,
            policy_decision=policy_decision,
            diagnostic_refs=(),
        )

    async def _dispatch_tool_call_with_bounds(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        batch_deadline: float | None,
    ) -> tuple[ToolExecutionOutcome, ToolPolicyDecision | None]:
        """按批级 timeout 与 cancellation token 包裹业务工具调用。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param batch_deadline: 批级 timeout 单调时钟 deadline；无 timeout 时为 ``None``。
        :returns: 工具 outcome；若由 ToolRuntime runtime 治理产生失败，则同时返回治理决策。
        """

        timeout_seconds = _remaining_batch_timeout_seconds(batch_deadline)
        if timeout_seconds is not None and timeout_seconds <= 0:
            decision = _runtime_timeout_policy_decision(elapsed_seconds=0.0)
            return _governed_failure_outcome(decision), decision
        if context.cancellation_token.is_cancelled():
            decision = _runtime_cancelled_policy_decision(
                context.cancellation_token.cancel_reason()
            )
            return _governed_failure_outcome(decision), decision
        try:
            capsule = self._execution_capsule_factory.create_capsule(
                call,
                context,
                self._dispatcher,
            )
        except Exception as exc:
            return (
                _tool_failed_outcome(
                    error=_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR,
                    message=(
                        "tool execution capsule build failed: "
                        f"{exc.__class__.__name__}: {exc}"
                    ),
                    hint=None,
                ),
                None,
            )
        capsule_task = asyncio.create_task(capsule.run())
        try:
            wait_result = await wait_for_or_cancel(
                capsule_task,
                token=context.cancellation_token,
                timeout_seconds=timeout_seconds,
            )
        except asyncio.CancelledError:
            await self._interrupt_capsule_after_wait(
                capsule=capsule,
                capsule_task=capsule_task,
                reason="tool execution task cancelled",
            )
            raise
        if isinstance(wait_result, WaitCompleted):
            try:
                return wait_result.value, None
            finally:
                await capsule.close()
        if isinstance(wait_result, WaitCancelled):
            await self._interrupt_capsule_after_wait(
                capsule=capsule,
                capsule_task=capsule_task,
                reason=wait_result.reason or "tool execution cancelled",
            )
            decision = _runtime_cancelled_policy_decision(wait_result.reason)
            return _governed_failure_outcome(decision), decision
        if isinstance(wait_result, WaitTimedOut):
            await self._interrupt_capsule_after_wait(
                capsule=capsule,
                capsule_task=capsule_task,
                reason="tool execution timed out",
            )
            decision = _runtime_timeout_policy_decision(
                elapsed_seconds=wait_result.elapsed_seconds
            )
            return _governed_failure_outcome(decision), decision
        raise TypeError("unsupported ToolRuntime wait outcome")

    async def _interrupt_capsule_after_wait(
        self,
        *,
        capsule: ToolExecutionCapsule,
        capsule_task: asyncio.Task[ToolExecutionOutcome],
        reason: str,
    ) -> None:
        """在 cancel / timeout 后中止 capsule 并释放资源。

        :param capsule: 当前工具调用 capsule。
        :param capsule_task: 正在等待的 capsule task。
        :param reason: interrupt 诊断原因。
        :returns: ``None``。
        """

        capsule.request_interrupt(reason)
        terminate_result = await capsule.terminate(reason)
        kill_result: ToolInterruptStepResult | None = None
        if terminate_result.supported and not terminate_result.completed:
            kill_result = await capsule.kill(reason)
        if not capsule_task.done():
            capsule_task.cancel()
            try:
                await capsule_task
            except asyncio.CancelledError:
                pass
        try:
            await capsule.close()
        except Exception as exc:
            _LOGGER.warning(
                "host.tool_runtime.capsule_close_failed session_id=%s run_id=%s "
                "attempt_id=%s execution_id=%s mode=%s reason=%s error_type=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                self._execution_scope.execution_id,
                capsule.mode.value,
                reason,
                exc.__class__.__name__,
                exc_info=True,
            )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.tool_runtime.capsule_interrupted session_id=%s run_id=%s "
            "attempt_id=%s execution_id=%s mode=%s reason=%s "
            "terminate_supported=%s terminate_completed=%s "
            "kill_supported=%s kill_completed=%s",
            self._execution_scope.session_id,
            self._execution_scope.run_id,
            self._execution_scope.attempt_id,
            self._execution_scope.execution_id,
            capsule.mode.value,
            reason,
            terminate_result.supported,
            terminate_result.completed,
            kill_result.supported if kill_result is not None else False,
            kill_result.completed if kill_result is not None else False,
        )

    async def _accept_reuse(
        self,
        *,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        normalized_arguments_digest: str,
        duplicate_decision: DuplicateDecision,
        policy_decision: ToolPolicyDecision,
        tool_idempotency_key: str | None,
        diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...],
    ) -> BatchToolExecutionRecord:
        """接受 duplicate reuse governance 并返回 prior outcome。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param normalized_arguments_digest: 参数 digest。
        :param duplicate_decision: duplicate reuse 决策。
        :param policy_decision: reuse policy decision。
        :param tool_idempotency_key: 工具级幂等 key。
        :param diagnostic_refs: 已发出的 duplicate 诊断 refs。
        :returns: 单次工具调用记录。
        :raises RuntimeError: reuse 决策缺少 prior outcome 时抛出。
        """

        if duplicate_decision.prior_outcome is None:
            raise RuntimeError("duplicate reuse requires prior accepted outcome")
        candidate = _tool_fact_reuse_accept_candidate(
            scope=self._execution_scope,
            effective_bundle=self._effective_bundle,
            call=call,
            iteration_id=context.iteration_id,
            normalized_arguments_digest=normalized_arguments_digest,
            prior_outcome=duplicate_decision.prior_outcome,
            policy_decision=policy_decision,
            duplicate_decision=duplicate_decision,
            tool_idempotency_key=tool_idempotency_key,
            diagnostic_refs=diagnostic_refs,
        )
        accept_result = await self._accept_with_retry(candidate)
        if isinstance(accept_result, ToolFactAcceptedAck):
            return BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=duplicate_decision.prior_outcome,
            )
        return BatchToolExecutionRecord(
            tool_call_id=call.tool_call_id,
            outcome=_accept_failure_outcome(accept_result),
        )

    async def _accept_awaiting(
        self,
        *,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
        normalized_arguments_digest: str,
        schema_digest: str,
        identity_digest: str,
        awaiting_outcome: ToolAwaitingOutcome,
        duplicate_request: DuplicateGovernanceRequest,
        duplicate_decision: DuplicateDecision,
        policy_decision: ToolPolicyDecision,
        diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...],
    ) -> _AwaitingAcceptExecution:
        """通过 Host awaiting accept path 接受等待型工具 outcome。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :param normalized_arguments_digest: 参数 digest。
        :param schema_digest: 工具 schema digest。
        :param identity_digest: 工具身份 digest。
        :param awaiting_outcome: 工具等待 outcome。
        :param duplicate_request: duplicate 查询输入。
        :param duplicate_decision: duplicate 决策。
        :param policy_decision: 工具治理决策。
        :param diagnostic_refs: 已发出的 duplicate 诊断 refs。
        :returns: awaiting accept 内部执行结果。
        """

        if (
            self._awaiting_accept_port is None
            or self._wait_adapter_registry is None
        ):
            return _AwaitingAcceptExecution(
                record=BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=self._awaiting_configuration_failure(),
                ),
                duplicate_terminal_recorded=False,
                durable_missing_reason=None,
            )
        binding = self._wait_adapter_registry.resolve_binding(
            tool_name=call.name,
            await_kind=awaiting_outcome.await_spec.await_kind,
        )
        if binding is None:
            return _AwaitingAcceptExecution(
                record=BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=self._awaiting_configuration_failure(),
                ),
                duplicate_terminal_recorded=False,
                durable_missing_reason=None,
            )
        external_job_ref = binding.external_job_ref(awaiting_outcome.await_spec)
        if (
            binding.resume_policy is WaitResumePolicy.POLL
            and external_job_ref is None
        ):
            return _AwaitingAcceptExecution(
                record=BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=self._awaiting_external_job_failure(),
                ),
                duplicate_terminal_recorded=False,
                durable_missing_reason=None,
            )
        snapshot_ref = _wait_snapshot_ref(awaiting_outcome)
        candidate = _tool_awaiting_accept_candidate(
            scope=self._execution_scope,
            call=call,
            iteration_id=context.iteration_id,
            tool_schema_digest=schema_digest,
            tool_identity_digest=identity_digest,
            normalized_arguments_digest=normalized_arguments_digest,
            awaiting_outcome=awaiting_outcome,
            snapshot_ref=snapshot_ref,
            binding=binding,
            external_job_ref=external_job_ref,
            duplicate_decision=duplicate_decision,
            policy_decision=policy_decision,
        )
        accept_result = await self._accept_awaiting_with_retry(candidate)
        if isinstance(accept_result, ToolAwaitingAcceptedAck):
            # Awaiting durable truth 已由 Host accepted ack 成立。attempt-local
            # marker 只是 cleanup/fanout 辅助状态，失败时不得覆盖 owner 返回。
            duplicate_terminal_recorded = (
                await self._record_duplicate_awaiting_accepted(
                    duplicate_request=duplicate_request,
                    accepted_ack=accept_result,
                    awaiting_outcome=awaiting_outcome,
                    duplicate_decision=duplicate_decision,
                    policy_decision=policy_decision,
                )
            )
            if not context.cancellation_token.is_cancelled():
                self._activate_accepted_wait_best_effort(
                    binding=binding,
                    tool_name=call.name,
                    awaiting_outcome=awaiting_outcome,
                    accepted_ack=accept_result,
                )
            return _AwaitingAcceptExecution(
                record=BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=awaiting_outcome,
                ),
                duplicate_terminal_recorded=duplicate_terminal_recorded,
                durable_missing_reason=None,
            )
        durable_missing_reason = _durable_missing_reason_for_awaiting_accept_result(
            accept_result
        )
        return _AwaitingAcceptExecution(
            record=BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=_awaiting_accept_failure_outcome(accept_result),
            ),
            duplicate_terminal_recorded=False,
            durable_missing_reason=durable_missing_reason,
        )

    def _activate_accepted_wait_best_effort(
        self,
        *,
        binding: WaitAdapterBinding,
        tool_name: str,
        awaiting_outcome: ToolAwaitingOutcome,
        accepted_ack: ToolAwaitingAcceptedAck,
    ) -> None:
        """在 Host accepted wait 后 best-effort 触发 provider activation。

        :param binding: 当前 awaiting outcome 使用的 Host wait binding。
        :param tool_name: 当前工具名。
        :param awaiting_outcome: 已 accepted 的 awaiting outcome。
        :param accepted_ack: Host awaiting accepted ack。
        :returns: ``None``。
        :raises: 不向调用方传播 activation adapter 异常。
        """

        if self._wait_activation_registry is None:
            return
        adapter = self._wait_activation_registry.resolve_adapter(
            binding.adapter_key
        )
        if adapter is None:
            return
        request = WaitActivationRequest(
            tool_name=tool_name,
            await_spec=awaiting_outcome.await_spec,
            accepted_ack=accepted_ack,
        )
        try:
            adapter.activate_accepted_wait(request)
        except Exception as exc:
            _LOGGER.warning(
                "host.tool_runtime.wait_activation_failed "
                "session_id=%s run_id=%s attempt_id=%s tool_name=%s "
                "adapter_key=%s error_type=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                tool_name,
                binding.adapter_key.value,
                exc.__class__.__name__,
            )
            self._emit_wait_activation_diagnostic_best_effort(exc)

    def _emit_wait_activation_diagnostic_best_effort(self, exc: Exception) -> None:
        """best-effort 发出 accepted wait activation 失败诊断。

        :param exc: activation adapter 抛出的异常。
        :returns: ``None``。
        :raises: 不向调用方传播诊断失败。
        """

        try:
            self._diagnostic_emitter.emit(
                ToolTraceDiagnosticRecord(
                    reason_code=_TOOL_RUNTIME_WAIT_ACTIVATION_FAILURE_REASON,
                    message=(
                        "wait activation adapter failed after accepted wait: "
                        f"{exc.__class__.__name__}"
                    ),
                ),
            )
        except Exception:
            _LOGGER.warning(
                "host.tool_runtime.wait_activation_diagnostic_failed "
                "session_id=%s run_id=%s attempt_id=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                exc_info=True,
            )

    def _awaiting_fanout_record(
        self, *, call: ToolCallRequest, duplicate_decision: DuplicateDecision
    ) -> BatchToolExecutionRecord:
        """返回防御性 awaiting fanout 的单次工具记录。

        :param call: 当前重复工具调用。
        :param duplicate_decision: awaiting fanout duplicate 决策。
        :returns: 指向 owner awaiting outcome 的工具执行记录。
        :raises RuntimeError: duplicate 决策缺少 awaiting outcome 时抛出。
        """

        if duplicate_decision.prior_awaiting_outcome is None:
            raise RuntimeError("awaiting fanout requires prior awaiting outcome")
        return BatchToolExecutionRecord(
            tool_call_id=call.tool_call_id,
            outcome=duplicate_decision.prior_awaiting_outcome,
        )

    def _awaiting_configuration_failure(self) -> ToolFailedOutcome:
        """构造后台任务启动能力未配置的受治理错误。

        :returns: 工具失败 outcome。
        """

        self._diagnostic_emitter.emit(
            ToolTraceDiagnosticRecord(
                reason_code=_TOOL_RUNTIME_AWAITING_BINDING_REASON,
                message="ToolAwaitingOutcome has no Host wait adapter binding",
            )
        )
        return _governed_failure_outcome(
            ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
                reason_code=_TOOL_RUNTIME_AWAITING_BINDING_REASON,
                message="该工具当前无法启动后台任务；请改用已可用的工具或稍后重试。",
            )
        )

    def _awaiting_external_job_failure(self) -> ToolFailedOutcome:
        """构造后台任务缺少可跟踪任务引用的受治理错误。

        :returns: 工具失败 outcome。
        """

        self._diagnostic_emitter.emit(
            ToolTraceDiagnosticRecord(
                reason_code=_TOOL_RUNTIME_AWAITING_EXTERNAL_JOB_REASON,
                message="awaiting binding did not produce external job ref",
            )
        )
        return _governed_failure_outcome(
            ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
                reason_code=_TOOL_RUNTIME_AWAITING_EXTERNAL_JOB_REASON,
                message="该工具后台任务未返回可跟踪的任务引用；请稍后重试或联系系统维护者。",
            )
        )

    async def _accept_awaiting_with_retry(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """通过 Host awaiting accept barrier 有限重试等待 ack。

        :param candidate: awaiting candidate。
        :returns: awaiting accept 结果；rejected ack 不重试。
        """

        if self._awaiting_accept_port is None:
            raise RuntimeError("awaiting accept port is required")
        attempt_count = 0
        last_error_code: str | None = None
        diagnostics: tuple[str, ...] = ()
        while attempt_count < self._retry_policy.max_attempts:
            attempt_count += 1
            try:
                result = self._awaiting_accept_port.accept_tool_awaiting(
                    candidate
                )
            except HostTransactionRetryExhaustedError:
                last_error_code = _TOOL_RUNTIME_ACCEPT_EXCEPTION_REASON
                result = ToolAwaitingAcceptTimedOut(
                    attempt_count=attempt_count,
                    last_error_code=last_error_code,
                    diagnostic_refs=diagnostics,
                )
            if isinstance(result, ToolAwaitingAcceptedAck | ToolAwaitingRejectedAck):
                return result
            last_error_code = result.last_error_code
            diagnostics = tuple(result.diagnostic_refs)
            if attempt_count >= self._retry_policy.max_attempts:
                break
            if self._retry_policy.backoff_seconds > 0:
                await asyncio.sleep(self._retry_policy.backoff_seconds)
        timeout_ref = self._diagnostic_emitter.emit(
            ToolTraceDiagnosticRecord(
                reason_code=_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON,
                message="tool awaiting accept ack was not received after bounded retry",
            )
        )
        return ToolAwaitingAcceptTimedOut(
            attempt_count=attempt_count,
            last_error_code=last_error_code,
            diagnostic_refs=(*diagnostics, timeout_ref.ref_id),
        )

    def _diagnostic_refs_for_duplicate(
        self, duplicate_decision: DuplicateDecision
    ) -> tuple[ToolTraceDiagnosticRef, ...]:
        """为非 allow duplicate 决策发出诊断 refs。

        :param duplicate_decision: duplicate governance 决策。
        :returns: 诊断引用；allow 决策返回空元组。
        """

        if duplicate_decision.kind is DuplicateDecisionKind.ALLOW:
            return ()
        if duplicate_decision.diagnostic_message is None:
            raise ValueError("duplicate decision requires diagnostic_message")
        ref = self._diagnostic_emitter.emit(
            ToolTraceDiagnosticRecord(
                reason_code=_duplicate_reason_code(duplicate_decision.kind),
                message=duplicate_decision.diagnostic_message,
            )
        )
        return (ref,)

    async def _record_duplicate_accepted(
        self,
        *,
        duplicate_request: DuplicateGovernanceRequest,
        accepted_ack: ToolFactAcceptedAck,
        accepted_outcome: ToolExecutionOutcome,
        duplicate_decision: DuplicateDecision,
        policy_decision: ToolPolicyDecision,
    ) -> bool:
        """在 accepted ack 后写入 attempt-local duplicate index。

        :param duplicate_request: duplicate 查询输入。
        :param accepted_ack: Host accepted ack。
        :param accepted_outcome: 已 accepted 的工具 outcome。
        :param duplicate_decision: 本次 duplicate 决策。
        :param policy_decision: 本次工具治理决策。
        :returns: 已写入 duplicate accepted index 时返回 ``True``。
        """

        if (
            policy_decision.kind is not ToolPolicyDecisionKind.ALLOW
            or duplicate_decision.kind is not DuplicateDecisionKind.ALLOW
        ):
            return False
        try:
            await self._duplicate_governance.record_accepted(
                duplicate_request,
                DuplicateAcceptedEntry(
                    accepted_event_refs=accepted_ack.accepted_event_refs,
                    accepted_outcome=accepted_outcome,
                    result_digest=accepted_ack.result_digest,
                ),
            )
        except Exception:
            self._diagnostic_emitter.emit(
                ToolTraceDiagnosticRecord(
                    reason_code="duplicate_accepted_index_failed",
                    message=(
                        "工具结果已完成持久化接受；重复调用索引更新失败，"
                        "后续治理必须以已持久化事实为准。"
                    ),
                )
            )
        return True

    async def _record_duplicate_awaiting_accepted(
        self,
        *,
        duplicate_request: DuplicateGovernanceRequest,
        accepted_ack: ToolAwaitingAcceptedAck,
        awaiting_outcome: ToolAwaitingOutcome,
        duplicate_decision: DuplicateDecision,
        policy_decision: ToolPolicyDecision,
    ) -> bool:
        """在 awaiting accepted ack 后 best-effort 写入 terminal marker。

        :param duplicate_request: duplicate 查询输入。
        :param accepted_ack: Host awaiting accepted ack。
        :param awaiting_outcome: 已被 Host 接受的 awaiting outcome。
        :param duplicate_decision: 本次 duplicate 决策。
        :param policy_decision: 本次工具治理决策。
        :returns: terminal 已处理时返回 ``True``；不适用 marker 时返回 ``False``。
        :raises: 不传播 marker 写入或诊断失败。
        """

        if (
            policy_decision.kind is not ToolPolicyDecisionKind.ALLOW
            or duplicate_decision.kind is not DuplicateDecisionKind.ALLOW
        ):
            return False
        awaiting_entry = DuplicateAwaitingAcceptedEntry(
            accepted_event_refs=tuple(
                HostEventRef(
                    event_id=event_ref.event_id,
                    event_sequence=event_ref.event_sequence,
                )
                for event_ref in accepted_ack.accepted_event_refs
            ),
            wait_id=accepted_ack.wait_id,
            awaiting_outcome=awaiting_outcome,
            result_digest=accepted_ack.result_digest,
        )
        try:
            await self._duplicate_governance.record_awaiting_accepted(
                duplicate_request,
                awaiting_entry,
            )
        except Exception as exc:
            _LOGGER.warning(
                "host.tool_runtime.duplicate_awaiting_marker_failed "
                "session_id=%s run_id=%s attempt_id=%s tool_name=%s "
                "wait_id=%s error_type=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                duplicate_request.tool_name,
                accepted_ack.wait_id,
                exc.__class__.__name__,
                exc_info=True,
            )
            self._emit_duplicate_awaiting_marker_diagnostic_best_effort(
                exc,
                accepted_ack.wait_id,
            )
        return True

    def _emit_duplicate_awaiting_marker_diagnostic_best_effort(
        self, exc: Exception, wait_id: str
    ) -> None:
        """best-effort 发出 awaiting marker 写入失败诊断。

        :param exc: marker 写入抛出的异常。
        :param wait_id: Host 已 accepted 的等待记录 id，仅用于诊断日志。
        :returns: ``None``。
        :raises: 不向调用方传播诊断失败。
        """

        try:
            self._diagnostic_emitter.emit(
                ToolTraceDiagnosticRecord(
                    reason_code=(
                        _TOOL_RUNTIME_DUPLICATE_AWAITING_MARKER_FAILURE_REASON
                    ),
                    message=(
                        "duplicate awaiting accepted marker failed: "
                        f"{exc.__class__.__name__}"
                    ),
                ),
            )
        except Exception:
            _LOGGER.warning(
                "host.tool_runtime.duplicate_awaiting_marker_diagnostic_failed "
                "session_id=%s run_id=%s attempt_id=%s wait_id=%s",
                self._execution_scope.session_id,
                self._execution_scope.run_id,
                self._execution_scope.attempt_id,
                wait_id,
                exc_info=True,
            )

    def _normalize_runtime_outcome(
        self,
        outcome: ToolExecutionOutcome,
        policy_decision: ToolPolicyDecision,
    ) -> tuple[ToolExecutionOutcome, ToolPolicyDecision]:
        """归一化普通工具 outcome。

        P7-S2 起 awaiting outcome 已在调用点分流到 Host awaiting accept
        path；本 helper 当前只保留普通工具 outcome 的扩展点，避免后续治理
        归一化重新混入 awaiting 分支。

        :param outcome: dispatcher 返回的工具 outcome。
        :param policy_decision: 当前治理决策。
        :returns: 可进入 accept path 的 outcome 与 policy decision。
        """

        return outcome, policy_decision

    async def _accept_with_retry(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """通过 Host accept barrier 有限重试等待 ack。

        :param candidate: 工具事实候选。
        :returns: accept 结果；rejected ack 不重试。
        """

        attempt_count = 0
        last_error_code: str | None = None
        diagnostics: tuple[ToolTraceDiagnosticRef, ...] = ()
        while attempt_count < self._retry_policy.max_attempts:
            attempt_count += 1
            try:
                result = self._accept_port.accept_tool_fact(candidate)
            except HostTransactionRetryExhaustedError:
                last_error_code = _TOOL_RUNTIME_ACCEPT_EXCEPTION_REASON
                result = ToolFactAcceptTimedOut(
                    attempt_count=attempt_count,
                    last_error_code=last_error_code,
                    diagnostic_refs=diagnostics,
                )
            if isinstance(result, ToolFactRejectedAck) and not result.diagnostic_refs:
                reject_ref = self._diagnostic_emitter.emit(
                    ToolTraceDiagnosticRecord(
                        reason_code=_TOOL_RUNTIME_ACCEPT_REJECTED_REASON,
                        message="tool fact accept candidate was rejected",
                    )
                )
                result = replace(result, diagnostic_refs=(reject_ref,))
            if isinstance(result, ToolFactAcceptedAck | ToolFactRejectedAck):
                return result
            last_error_code = result.last_error_code
            diagnostics = result.diagnostic_refs
            if attempt_count >= self._retry_policy.max_attempts:
                break
            if self._retry_policy.backoff_seconds > 0:
                await asyncio.sleep(self._retry_policy.backoff_seconds)
        timeout_ref = self._diagnostic_emitter.emit(
            ToolTraceDiagnosticRecord(
                reason_code=_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON,
                message="tool fact accept ack was not received after bounded retry",
            )
        )
        return ToolFactAcceptTimedOut(
            attempt_count=attempt_count,
            last_error_code=last_error_code,
            diagnostic_refs=(*diagnostics, timeout_ref),
        )


@dataclass(frozen=True, slots=True)
class ToolRuntimeHandle:
    """RunInputBuilder 与 EngineWorker 使用的 ToolRuntime handle。

    :param effective_bundle: attempt-local effective bundle。
    :param tool_schemas: Engine 可见 schemas，必须来自 ``effective_bundle``。
    :param tool_executor: Engine 使用的批式 ToolExecutor。
    """

    effective_bundle: EffectiveToolBundle
    tool_schemas: tuple[ToolSchema, ...]
    tool_executor: ToolExecutor

    def __post_init__(self) -> None:
        """校验 handle 中 schemas 与 effective bundle 同源。

        :returns: ``None``。
        :raises ValueError: ``tool_schemas`` 不是 effective bundle 的投影时抛出。
        """

        if self.tool_schemas != self.effective_bundle.tool_schemas:
            raise ValueError(
                "ToolRuntimeHandle.tool_schemas must come from effective bundle"
            )


class ToolRuntimeFactory(Protocol):
    """ToolRuntime handle factory 协议。"""

    def create_tool_runtime(
        self, request: ToolRuntimeBuildRequest
    ) -> ToolRuntimeHandle:
        """构造 ToolRuntime handle。

        :param request: ToolRuntime 构造输入。
        :returns: ToolRuntimeHandle。
        """
        ...


class DefaultToolRuntimeFactory:
    """默认 ToolRuntime handle factory。

    当构造请求提供 execution scope 与 accept port 时创建真实
    ``ToolRuntimeExecutor``；未提供时保留未连接 executor，避免没有 Host
    accept barrier 的装配路径误执行业务工具。
    """

    def __init__(self, bundle_builder: EffectiveToolBundleBuilder) -> None:
        """初始化 factory。

        :param bundle_builder: effective bundle builder。
        :returns: ``None``。
        """

        self._bundle_builder = bundle_builder

    def create_tool_runtime(
        self, request: ToolRuntimeBuildRequest
    ) -> ToolRuntimeHandle:
        """构造 ToolRuntimeHandle。

        :param request: ToolRuntime 构造输入。
        :returns: 同源暴露 schema 与 executor 的 handle。
        """

        effective_bundle = self._bundle_builder.build(
            request.effective_bundle_request
        )
        if request.execution_scope is not None and request.accept_port is not None:
            diagnostic_emitter = (
                request.diagnostic_emitter
                if request.diagnostic_emitter is not None
                else DeterministicToolTraceDiagnosticEmitter()
            )
            truncation_port: TruncationPort
            if request.effective_bundle_request.enable_truncation_manager:
                # TruncationManager 是 run-scoped 轻量对象：构造期只保存
                # identity、effective bundle 的截断声明只读视图和空 cursor
                # dict；不打开文件、DB、后台任务或 durable cursor table。
                truncation_manager = TruncationManager(
                    session_id=request.execution_scope.session_id,
                    run_id=request.execution_scope.run_id,
                    attempt_id=request.execution_scope.attempt_id,
                    truncate_specs_by_name=effective_bundle.truncate_specs_by_name,
                )
                if effective_bundle.fetch_more_callable is not None:
                    effective_bundle.fetch_more_callable.bind_manager(
                        truncation_manager
                    )
                truncation_port = truncation_manager
            else:
                truncation_port = NoopTruncationPort()
            policy_port = DefaultToolRuntimePolicyPort(
                execution_scope=request.execution_scope,
                policy_view=request.policy_view,
            )
            duplicate_governance = InMemoryAttemptDuplicateGovernance(
                request.duplicate_governance_policy
            )
            execution_capsule_factory = (
                request.execution_capsule_factory
                if request.execution_capsule_factory is not None
                else DeclaredToolExecutionCapsuleFactory(
                    effective_bundle,
                    request.process_capsule_interrupt_policy,
                )
            )
            executor: ToolExecutor = ToolRuntimeExecutor(
                effective_bundle=effective_bundle,
                execution_scope=request.execution_scope,
                dispatcher=DefaultToolDispatcher(effective_bundle),
                policy_port=policy_port,
                duplicate_governance=duplicate_governance,
                truncation_port=truncation_port,
                accept_port=request.accept_port,
                awaiting_accept_port=request.awaiting_accept_port,
                wait_adapter_registry=request.wait_adapter_registry,
                wait_activation_registry=request.wait_activation_registry,
                retry_policy=request.retry_policy,
                policy_view=request.policy_view,
                diagnostic_emitter=diagnostic_emitter,
                execution_capsule_factory=execution_capsule_factory,
            )
        else:
            executor = ToolRuntimeUnsupportedExecutor(effective_bundle)
        return ToolRuntimeHandle(
            effective_bundle=effective_bundle,
            tool_schemas=effective_bundle.tool_schemas,
            tool_executor=executor,
        )


@dataclass(frozen=True, slots=True)
class _SelectedTruncationValue:
    """待截断的 JSON 值。

    :param value: 从工具结果中选出的目标值。
    """

    value: JsonValue


@dataclass(frozen=True, slots=True)
class _CreatedTruncation:
    """一次截断产生的可见值与剩余引用。

    :param visible_value: 截断后可直接返回给 LLM 的值。
    :param remaining_ref: run-local 剩余内容引用。
    """

    visible_value: JsonValue
    remaining_ref: TruncatedRemainderRef


@dataclass(frozen=True, slots=True)
class _AcceptContext:
    """accept precondition 读取结果。

    :param run: durable Run row；不存在时为 ``None``。
    :param attempt: durable Attempt row；不存在时为 ``None``。
    :param dispatch_record: durable dispatch record row；不存在时为 ``None``。
    """

    run: RunRow | None
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None


@dataclass(frozen=True, slots=True)
class _ToolAcceptEventPlan:
    """工具 accept path 的稳定事件 id 规划。

    :param tool_fact_id: 稳定工具事实 id。
    :param requested_id: ``TOOL_CALL_REQUESTED`` 事件 id。
    :param governed_id: ``TOOL_CALL_GOVERNED`` 事件 id。
    :param result_id: ``TOOL_RESULT_ACCEPTED`` 事件 id。
    """

    tool_fact_id: str
    requested_id: str
    governed_id: str
    result_id: str


@dataclass(frozen=True, slots=True)
class _ToolResultPayloadPlan:
    """``TOOL_RESULT_ACCEPTED`` 的冷热 payload 写入计划。

    :param inline_payload: 写入 EventLog ``payload_json`` 的热 payload。
    :param payload_ref: EventLog row 需要挂载的冷 payload descriptor；无则为
        ``None``。
    """

    inline_payload: Mapping[str, JsonValue]
    payload_ref: HostPayloadRef | None


def _log_tool_fact_accept_result(
    candidate: ToolFactAcceptCandidate, result: ToolFactAcceptResult
) -> None:
    """记录工具事实 accept barrier 的有界结果。

    :param candidate: 工具事实候选。
    :param result: accept barrier 结果。
    :returns: ``None``。
    """

    if isinstance(result, ToolFactAcceptedAck):
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            (
                "host.tool_runtime.accept_tool_fact.committed "
                "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
                "tool_call_id=%s tool_name=%s tool_fact_kind=%s "
                "tool_fact_id=%s tool_result_event_id=%s accepted_event_count=%s"
            ),
            candidate.identity.session_id,
            candidate.identity.run_id,
            candidate.identity.attempt_id,
            candidate.identity.execution_id,
            candidate.call.tool_call_id,
            candidate.call.tool_name,
            candidate.tool_fact_kind.value,
            result.tool_fact_id,
            None
            if result.tool_result_event_ref is None
            else result.tool_result_event_ref.event_id,
            len(result.accepted_event_refs),
        )
        return
    if isinstance(result, ToolFactRejectedAck):
        _LOGGER.debug(
            (
                "host.tool_runtime.accept_tool_fact.rejected "
                "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
                "tool_call_id=%s tool_name=%s reason=%s retryable=%s"
            ),
            candidate.identity.session_id,
            candidate.identity.run_id,
            candidate.identity.attempt_id,
            candidate.identity.execution_id,
            candidate.call.tool_call_id,
            candidate.call.tool_name,
            result.reason_code.value,
            result.retryable,
        )
        return
    _LOGGER.debug(
        (
            "host.tool_runtime.accept_tool_fact.timed_out "
            "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
            "tool_call_id=%s tool_name=%s attempt_count=%s last_error_code=%s"
        ),
        candidate.identity.session_id,
        candidate.identity.run_id,
        candidate.identity.attempt_id,
        candidate.identity.execution_id,
        candidate.call.tool_call_id,
        candidate.call.tool_name,
        result.attempt_count,
        result.last_error_code,
    )


def _accept_idempotency_scope(candidate: ToolFactAcceptCandidate) -> IdempotencyScope:
    """构造工具事实 accept 幂等作用域。

    :param candidate: 工具事实候选。
    :returns: 幂等作用域。
    """

    return IdempotencyScope(
        scope_kind=_TOOL_FACT_ACCEPT_SCOPE_KIND,
        scope_id=(
            f"{candidate.identity.attempt_id}:"
            f"{candidate.call.tool_call_id}"
        ),
        idempotency_key=candidate.idempotency.accept_idempotency_key,
    )


def _read_accept_context(
    transaction: HostTransaction, candidate: ToolFactAcceptCandidate
) -> _AcceptContext:
    """读取 accept precondition 所需 durable rows。

    :param transaction: 当前 Host transaction。
    :param candidate: 工具事实候选。
    :returns: durable context。
    """

    return _AcceptContext(
        run=read_run_by_id(transaction, candidate.identity.run_id),
        attempt=read_attempt_by_id(transaction, candidate.identity.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, candidate.identity.attempt_id
        ),
    )


def _invalid_accept_context_reason(
    context: _AcceptContext, candidate: ToolFactAcceptCandidate
) -> ToolAcceptRejectReason | None:
    """判断 accept precondition 是否失败。

    :param context: durable context。
    :param candidate: 工具事实候选。
    :returns: 拒绝原因；可接受时为 ``None``。
    """

    if context.run is None or context.attempt is None:
        return ToolAcceptRejectReason.INVALID_ATTEMPT
    if context.dispatch_record is None:
        return ToolAcceptRejectReason.INVALID_ATTEMPT
    if (
        context.run.session_id != candidate.identity.session_id
        or context.run.run_id != candidate.identity.run_id
        or context.run.current_attempt_id != candidate.identity.attempt_id
        or context.attempt.run_id != candidate.identity.run_id
    ):
        return ToolAcceptRejectReason.INVALID_ATTEMPT
    if (
        context.attempt.execution_id != candidate.identity.execution_id
        or context.dispatch_record.execution_id != candidate.identity.execution_id
        or context.dispatch_record.run_id != candidate.identity.run_id
    ):
        return ToolAcceptRejectReason.STALE_EXECUTION
    if (
        context.run.status is not RunStatus.RUNNING
        or context.attempt.status is not AttemptStatus.RUNNING
        or context.dispatch_record.status is not DispatchRecordStatus.DISPATCHING
        or context.dispatch_record.worker_accept_event_id is None
    ):
        return ToolAcceptRejectReason.INVALID_ATTEMPT
    return None


def _candidate_payload_descriptor_exists(
    transaction: HostTransaction, candidate: ToolFactAcceptCandidate
) -> bool:
    """校验 candidate 的 payload descriptor 已持久化。

    :param transaction: 当前 Host transaction。
    :param candidate: 工具事实候选。
    :returns: 无 payload ref 或 descriptor 存在时返回 ``True``。
    """

    result = candidate.result
    if result is None or result.payload_ref is None:
        return True
    descriptor = read_payload_descriptor(
        transaction,
        result.payload_ref.payload_ref,
    )
    return (
        descriptor is not None
        and descriptor.payload_digest == result.payload_ref.payload_digest
    )


def _tool_accept_event_plan(candidate: ToolFactAcceptCandidate) -> _ToolAcceptEventPlan:
    """为工具 accept candidate 派生稳定事件 id。

    :param candidate: 工具事实候选。
    :returns: 事件 id 规划。
    """

    digest_input: dict[str, JsonValue] = {
        "session_id": candidate.identity.session_id,
        "run_id": candidate.identity.run_id,
        "attempt_id": candidate.identity.attempt_id,
        "execution_id": candidate.identity.execution_id,
        "iteration_id": candidate.call.iteration_id,
        "tool_call_id": candidate.call.tool_call_id,
        "tool_fact_kind": candidate.tool_fact_kind.value,
        "accept_idempotency_key": candidate.idempotency.accept_idempotency_key,
        "semantic_input_digest": candidate.idempotency.semantic_input_digest,
    }
    digest = sha256_digest_json(digest_input).removeprefix("sha256:")
    tool_fact_id = f"tool-fact-{digest}"
    return _ToolAcceptEventPlan(
        tool_fact_id=tool_fact_id,
        requested_id=f"{_EVENT_ID_TOOL_CALL_REQUESTED_PREFIX}{digest}",
        governed_id=f"{_EVENT_ID_TOOL_CALL_GOVERNED_PREFIX}{digest}",
        result_id=f"{_EVENT_ID_TOOL_RESULT_ACCEPTED_PREFIX}{digest}",
    )


def _tool_call_request_atom(
    candidate: ToolFactAcceptCandidate,
) -> AcceptedToolCallRequestAtomInput:
    """把普通工具 accepted candidate 显式映射为共享 request atom。

    :param candidate: 工具事实候选。
    :returns: 与 candidate 同源的 canonical request atom 输入。
    :raises HostPayloadReferenceError: 写 accepted fact 时缺少 accepted arguments
        时抛出。
    """

    return AcceptedToolCallRequestAtomInput(
        session_id=candidate.identity.session_id,
        run_id=candidate.identity.run_id,
        attempt_id=candidate.identity.attempt_id,
        execution_id=candidate.identity.execution_id,
        iteration_id=candidate.call.iteration_id,
        tool_call_id=candidate.call.tool_call_id,
        tool_name=candidate.call.tool_name,
        tool_schema_digest=candidate.call.tool_schema_digest,
        tool_identity_digest=candidate.call.tool_identity_digest,
        accepted_arguments=_required_accepted_arguments(candidate.call),
        normalized_arguments_digest=candidate.call.normalized_arguments_digest,
        tool_fact_kind=candidate.tool_fact_kind.value,
        accept_idempotency_key=candidate.idempotency.accept_idempotency_key,
        semantic_input_digest=candidate.idempotency.semantic_input_digest,
        semantic_query_text=candidate.call.semantic_query_text,
    )


def _append_tool_call_governed_if_needed(
    event_log_store: EventLogStore,
    transaction: HostTransaction,
    candidate: ToolFactAcceptCandidate,
    event_id: str,
    requested: EventLogRow,
) -> EventLogRow | None:
    """按 candidate 治理语义追加 ``TOOL_CALL_GOVERNED``。

    :param event_log_store: EventLog primitive。
    :param transaction: 当前 Host transaction。
    :param candidate: 工具事实候选。
    :param event_id: 稳定事件 id。
    :param requested: 已写入的 ``TOOL_CALL_REQUESTED`` row。
    :returns: 写入的 governed row；无需写入时为 ``None``。
    """

    if not _should_append_governed_event(candidate):
        return None
    duplicate = candidate.governance.duplicate
    return event_log_store.append_event(
        transaction,
        _tool_event_request(
            candidate,
            event_id=event_id,
            event_type=_EVENT_TYPE_TOOL_CALL_GOVERNED,
            policy_decision=_policy_decision_json(
                candidate.governance.policy_decision
            ),
            reason=_policy_reason_json(candidate.governance.policy_decision),
            payload={
                "session_id": candidate.identity.session_id,
                "run_id": candidate.identity.run_id,
                "attempt_id": candidate.identity.attempt_id,
                "execution_id": candidate.identity.execution_id,
                "iteration_id": candidate.call.iteration_id,
                "tool_call_id": candidate.call.tool_call_id,
                "tool_name": candidate.call.tool_name,
                "tool_fact_kind": candidate.tool_fact_kind.value,
                "tool_call_requested_event_ref": _event_ref_json(
                    _event_ref_from_row(requested)
                ),
                "policy_decision": _policy_decision_json(
                    candidate.governance.policy_decision
                ),
                "duplicate_key": (
                    duplicate.duplicate_key if duplicate is not None else None
                ),
                "duplicate_decision": (
                    duplicate.duplicate_decision.value
                    if duplicate is not None
                    else None
                ),
                "duplicate_scope": _duplicate_scope_json(
                    duplicate.duplicate_scope if duplicate is not None else None
                ),
                "reuse_prior_event_refs": [
                    _event_ref_json(ref)
                    for ref in _candidate_reuse_prior_event_refs(candidate)
                ],
                "tool_idempotency_key": (
                    candidate.governance.tool_idempotency_key
                ),
                "diagnostic_refs": [
                    _diagnostic_ref_json(ref)
                    for ref in candidate.diagnostics.diagnostic_refs
                ],
            },
        ),
    ).row


def _append_tool_result_if_needed(
    event_log_store: EventLogStore,
    transaction: HostTransaction,
    candidate: ToolFactAcceptCandidate,
    event_id: str,
    requested: EventLogRow,
    governed: EventLogRow | None,
) -> EventLogRow | None:
    """按 candidate 事实类别追加 ``TOOL_RESULT_ACCEPTED``。

    :param event_log_store: EventLog primitive。
    :param transaction: 当前 Host transaction。
    :param candidate: 工具事实候选。
    :param event_id: 稳定事件 id。
    :param requested: 已写入的 ``TOOL_CALL_REQUESTED`` row。
    :param governed: 已写入的 ``TOOL_CALL_GOVERNED`` row；无则为 ``None``。
    :returns: 写入的 result row；reuse 时为 ``None``。
    """

    if candidate.tool_fact_kind is ToolFactKind.REUSE:
        return None
    payload_plan = _tool_result_payload_plan(
        transaction=transaction,
        candidate=candidate,
        result_event_id=event_id,
        requested=requested,
        governed=governed,
    )
    payload_ref = (
        payload_plan.payload_ref.payload_ref
        if payload_plan.payload_ref is not None
        else None
    )
    payload_digest = (
        payload_plan.payload_ref.payload_digest
        if payload_plan.payload_ref is not None
        else None
    )
    return event_log_store.append_event(
        transaction,
        _tool_event_request(
            candidate,
            event_id=event_id,
            event_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            policy_decision=_policy_decision_json(
                candidate.governance.policy_decision
            ),
            reason=_policy_reason_json(candidate.governance.policy_decision),
            payload=payload_plan.inline_payload,
            payload_ref=payload_ref,
            payload_digest=payload_digest,
        ),
    ).row


def _tool_result_payload_plan(
    *,
    transaction: HostTransaction,
    candidate: ToolFactAcceptCandidate,
    result_event_id: str,
    requested: EventLogRow,
    governed: EventLogRow | None,
) -> _ToolResultPayloadPlan:
    """为 ``TOOL_RESULT_ACCEPTED`` 准备冷热 payload。

    小 payload 直接完整写入 EventLog inline；超过 durable inline 阈值时，
    完整 payload 写入 SQLite payload descriptor，EventLog inline 只保留可
    索引的热元数据与冷 payload 引用。

    :param transaction: 当前 Host transaction。
    :param candidate: 工具事实候选。
    :param result_event_id: 即将写入的 ``TOOL_RESULT_ACCEPTED`` event id。
    :param requested: 已写入的 ``TOOL_CALL_REQUESTED`` row。
    :param governed: 已写入的 ``TOOL_CALL_GOVERNED`` row；无则为 ``None``。
    :returns: EventLog payload 写入计划。
    """

    result = _candidate_result(candidate)
    inline_payload = _tool_result_payload(
        candidate=candidate,
        result_event_id=result_event_id,
        requested=requested,
        governed=governed,
        event_payload_ref=result.payload_ref,
        evidence_payload_ref=(
            result.payload_ref.payload_ref
            if result.payload_ref is not None
            else None
        ),
        evidence_payload_digest=(
            result.payload_ref.payload_digest
            if result.payload_ref is not None
            else result.payload_digest
        ),
        include_raw_tool_outcome=True,
    )
    if (
        result.payload_ref is not None
        or _payload_size_bytes(inline_payload)
        <= transaction.payload_inline_threshold_bytes
    ):
        return _ToolResultPayloadPlan(
            inline_payload=inline_payload,
            payload_ref=result.payload_ref,
        )

    payload_ref = _tool_result_payload_ref(result_event_id)
    cold_payload = _tool_result_payload(
        candidate=candidate,
        result_event_id=result_event_id,
        requested=requested,
        governed=governed,
        event_payload_ref=None,
        evidence_payload_ref=payload_ref,
        evidence_payload_digest=None,
        include_raw_tool_outcome=True,
    )
    descriptor = PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=_tool_result_sqlite_payload_id(result_event_id),
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=cold_payload,
            media_type="application/json",
            metadata={
                "event_type": _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
                "event_id": result_event_id,
                "tool_name": candidate.call.tool_name,
                "tool_call_id": candidate.call.tool_call_id,
            },
            expected_digest=None,
        ),
    )
    event_payload_ref = HostPayloadRef(
        payload_ref=descriptor.payload_ref,
        payload_digest=descriptor.payload_digest,
    )
    hot_payload = _tool_result_payload(
        candidate=candidate,
        result_event_id=result_event_id,
        requested=requested,
        governed=governed,
        event_payload_ref=event_payload_ref,
        evidence_payload_ref=descriptor.payload_ref,
        evidence_payload_digest=None,
        include_raw_tool_outcome=False,
    )
    return _ToolResultPayloadPlan(
        inline_payload=hot_payload,
        payload_ref=event_payload_ref,
    )


def _tool_result_payload(
    *,
    candidate: ToolFactAcceptCandidate,
    result_event_id: str,
    requested: EventLogRow,
    governed: EventLogRow | None,
    event_payload_ref: HostPayloadRef | None,
    evidence_payload_ref: str | None,
    evidence_payload_digest: str | None,
    include_raw_tool_outcome: bool,
) -> Mapping[str, JsonValue]:
    """构造 ``TOOL_RESULT_ACCEPTED`` payload。

    :param candidate: 工具事实候选。
    :param result_event_id: 即将写入的 ``TOOL_RESULT_ACCEPTED`` event id。
    :param requested: 已写入的 ``TOOL_CALL_REQUESTED`` row。
    :param governed: 已写入的 ``TOOL_CALL_GOVERNED`` row；无则为 ``None``。
    :param event_payload_ref: EventLog 热 payload 中暴露的冷 payload 引用。
    :param evidence_payload_ref: accepted evidence result ref 中的 payload ref。
    :param evidence_payload_digest: accepted evidence result ref 中的 payload digest。
    :param include_raw_tool_outcome: 是否包含完整 raw 工具 outcome。
    :returns: 可写入 EventLog 或 SQLite payload descriptor 的 JSON object。
    """

    result = _candidate_result(candidate)
    duplicate = candidate.governance.duplicate
    accepted_evidence_envelope = _accepted_evidence_envelope(
        candidate=candidate,
        result_event_id=result_event_id,
        requested=requested,
        payload_ref=evidence_payload_ref,
        payload_digest=evidence_payload_digest,
    )
    payload: dict[str, JsonValue] = {
        "session_id": candidate.identity.session_id,
        "run_id": candidate.identity.run_id,
        "attempt_id": candidate.identity.attempt_id,
        "execution_id": candidate.identity.execution_id,
        "iteration_id": candidate.call.iteration_id,
        "tool_call_id": candidate.call.tool_call_id,
        "tool_name": candidate.call.tool_name,
        "tool_fact_kind": candidate.tool_fact_kind.value,
        "tool_schema_digest": candidate.call.tool_schema_digest,
        "tool_identity_digest": candidate.call.tool_identity_digest,
        "normalized_arguments_digest": candidate.call.normalized_arguments_digest,
        "outcome_digest": result.outcome_digest,
        "payload_digest": result.payload_digest,
        "payload_ref": _payload_ref_json(event_payload_ref),
        "truncation": _truncation_json(result.truncation),
        "duplicate_key": (
            duplicate.duplicate_key if duplicate is not None else None
        ),
        "duplicate_decision": (
            duplicate.duplicate_decision.value
            if duplicate is not None
            else None
        ),
        "policy_decision": _policy_decision_json(
            candidate.governance.policy_decision
        ),
        "tool_idempotency_key": candidate.governance.tool_idempotency_key,
        "diagnostic_refs": [
            _diagnostic_ref_json(ref)
            for ref in candidate.diagnostics.diagnostic_refs
        ],
        "tool_call_requested_event_ref": _event_ref_json(
            _event_ref_from_row(requested)
        ),
        "tool_call_governed_event_ref": (
            _event_ref_json(_event_ref_from_row(governed))
            if governed is not None
                else None
        ),
        "accept_idempotency_key": candidate.idempotency.accept_idempotency_key,
        "semantic_input_digest": candidate.idempotency.semantic_input_digest,
        _PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE: (
            accepted_evidence_envelope_to_json_value(accepted_evidence_envelope)
        ),
        _PAYLOAD_FIELD_TOOL_TIMING: result.tool_timing,
        _PAYLOAD_FIELD_FAILURE_METADATA: result.failure_metadata,
    }
    if include_raw_tool_outcome:
        payload[_PAYLOAD_FIELD_RAW_TOOL_OUTCOME] = result.raw_tool_outcome
    return payload


def _payload_size_bytes(payload: Mapping[str, JsonValue]) -> int:
    """计算 payload canonical JSON 的 UTF-8 字节数。

    :param payload: JSON payload。
    :returns: canonical JSON UTF-8 字节数。
    """

    return len(canonical_json_dumps(payload).encode("utf-8"))


def _tool_result_payload_ref(result_event_id: str) -> str:
    """派生 ``TOOL_RESULT_ACCEPTED`` 冷 payload descriptor ref。

    :param result_event_id: ``TOOL_RESULT_ACCEPTED`` event id。
    :returns: 稳定 payload descriptor ref。
    """

    return f"{_TOOL_RESULT_PAYLOAD_REF_PREFIX}-{result_event_id}"


def _tool_result_sqlite_payload_id(result_event_id: str) -> str:
    """派生 ``TOOL_RESULT_ACCEPTED`` SQLite payload row id。

    :param result_event_id: ``TOOL_RESULT_ACCEPTED`` event id。
    :returns: 稳定 SQLite payload id。
    """

    return f"{_TOOL_RESULT_SQLITE_PAYLOAD_ID_PREFIX}-{result_event_id}"


def _accepted_evidence_envelope(
    *,
    candidate: ToolFactAcceptCandidate,
    result_event_id: str,
    requested: EventLogRow,
    payload_ref: str | None,
    payload_digest: str | None,
) -> AcceptedEvidenceEnvelope:
    """构造 accepted tool result 的 Host 中立证据信封。

    :param candidate: 工具事实候选。
    :param result_event_id: 即将写入的 ``TOOL_RESULT_ACCEPTED`` event id。
    :param requested: 已写入的 ``TOOL_CALL_REQUESTED`` row。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload digest。
    :returns: accepted evidence envelope。
    """

    result = _candidate_result(candidate)
    return AcceptedEvidenceEnvelope(
        evidence_id=derive_accepted_evidence_id(result_event_id),
        producer_event_ref=result_event_id,
        tool_name=candidate.call.tool_name,
        tool_call_id=candidate.call.tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=requested.event_id,
            normalized_arguments_digest=candidate.call.normalized_arguments_digest,
            semantic_input_digest=candidate.idempotency.semantic_input_digest,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            outcome_digest=result.outcome_digest,
            truncation_applied=(
                result.truncation.applied
                if result.truncation is not None
                else False
            ),
        ),
        source_refs=(),
        locator_refs=(),
    )


def _tool_event_request(
    candidate: ToolFactAcceptCandidate,
    *,
    event_id: str,
    event_type: str,
    policy_decision: JsonValue | None,
    reason: JsonValue | None,
    payload: Mapping[str, JsonValue],
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogAppendRequest:
    """构造工具 canonical EventLog append request。

    :param candidate: 工具事实候选。
    :param event_id: 稳定事件 id。
    :param event_type: Host event type。
    :param policy_decision: 顶层 policy decision JSON。
    :param reason: 顶层 reason JSON。
    :param payload: inline payload JSON。
    :param payload_ref: payload descriptor 引用；无则为 ``None``。
    :param payload_digest: payload descriptor digest；无则为 ``None``。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=candidate.identity.session_id,
        run_id=candidate.identity.run_id,
        attempt_id=candidate.identity.attempt_id,
        execution_id=candidate.identity.execution_id,
        event_type=event_type,
        occurred_at=datetime.now(UTC),
        actor=_TOOL_ACCEPT_EVENT_ACTOR,
        source=_TOOL_ACCEPT_EVENT_SOURCE,
        client_request_id=None,
        idempotency_key=candidate.idempotency.accept_idempotency_key,
        policy_decision=policy_decision,
        reason=reason,
        payload_json=payload,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )


def _should_append_governed_event(candidate: ToolFactAcceptCandidate) -> bool:
    """判断 candidate 是否需要 ``TOOL_CALL_GOVERNED``。

    :param candidate: 工具事实候选。
    :returns: 需要记录治理事实时返回 ``True``。
    """

    return (
        candidate.tool_fact_kind is ToolFactKind.REUSE
        or candidate.governance.policy_decision.kind
        is not ToolPolicyDecisionKind.ALLOW
        or (
            candidate.governance.duplicate is not None
            and candidate.governance.duplicate.duplicate_decision
            is not DuplicateDecisionKind.ALLOW
        )
    )


def _created_event_for_idempotency(
    requested: EventLogRow, governed: EventLogRow | None, result: EventLogRow | None
) -> EventLogRow:
    """选择幂等记录引用的创建事件。

    :param requested: ``TOOL_CALL_REQUESTED`` row。
    :param governed: ``TOOL_CALL_GOVERNED`` row；无则为 ``None``。
    :param result: ``TOOL_RESULT_ACCEPTED`` row；无则为 ``None``。
    :returns: 应写入 idempotency record 的 EventLog row。
    """

    if result is not None:
        return result
    if governed is not None:
        return governed
    return requested


def _accepted_ack_from_existing(
    event_log_store: EventLogStore,
    transaction: HostTransaction,
    candidate: ToolFactAcceptCandidate,
    record: IdempotencyRecord,
) -> ToolFactAcceptedAck:
    """从既有幂等记录重建 accepted ack。

    :param event_log_store: EventLog primitive。
    :param transaction: 当前 Host transaction。
    :param candidate: 工具事实候选。
    :param record: 既有幂等记录。
    :returns: accepted ack。
    :raises HostDurableError: 幂等记录指向的 EventLog 事实缺失时抛出。
    """

    plan = _tool_accept_event_plan(candidate)
    requested = _read_required_event(
        event_log_store, transaction, plan.requested_id
    )
    governed = event_log_store.read_event_by_id(transaction, plan.governed_id)
    result = event_log_store.read_event_by_id(transaction, plan.result_id)
    return _accepted_ack_from_rows(
        candidate=candidate,
        tool_fact_id=record.result_ref,
        requested=requested,
        governed=governed,
        result=result,
        idempotency_record=record,
    )


def _accepted_ack_from_rows(
    *,
    candidate: ToolFactAcceptCandidate,
    tool_fact_id: str,
    requested: EventLogRow,
    governed: EventLogRow | None,
    result: EventLogRow | None,
    idempotency_record: IdempotencyRecord,
) -> ToolFactAcceptedAck:
    """从 EventLog rows 组装 accepted ack。

    :param candidate: 工具事实候选。
    :param tool_fact_id: 稳定工具事实 id。
    :param requested: ``TOOL_CALL_REQUESTED`` row。
    :param governed: ``TOOL_CALL_GOVERNED`` row；无则为 ``None``。
    :param result: ``TOOL_RESULT_ACCEPTED`` row；无则为 ``None``。
    :param idempotency_record: 幂等记录。
    :returns: accepted ack。
    """

    requested_ref = _event_ref_from_row(requested)
    governed_ref = _event_ref_from_row(governed) if governed is not None else None
    result_ref = _event_ref_from_row(result) if result is not None else None
    event_refs = tuple(
        ref
        for ref in (requested_ref, governed_ref, result_ref)
        if ref is not None
    )
    result_payload_ref = (
        HostPayloadRef(result.payload_ref, result.payload_digest)
        if result is not None
        and result.payload_ref is not None
        and result.payload_digest is not None
        else None
    )
    return ToolFactAcceptedAck(
        accepted_event_refs=event_refs,
        tool_fact_id=tool_fact_id,
        tool_call_requested_event_ref=requested_ref,
        tool_call_governed_event_ref=governed_ref,
        tool_result_event_ref=result_ref,
        result_payload_ref=result_payload_ref,
        result_digest=_ack_result_digest(candidate),
        reuse_prior_event_refs=_candidate_reuse_prior_event_refs(candidate),
        diagnostic_refs=candidate.diagnostics.diagnostic_refs,
        idempotency_record_ref=_idempotency_record_ref(idempotency_record),
    )


def _read_required_event(
    event_log_store: EventLogStore,
    transaction: HostTransaction,
    event_id: str,
) -> EventLogRow:
    """读取必存在的 EventLog row。

    :param event_log_store: EventLog primitive。
    :param transaction: 当前 Host transaction。
    :param event_id: 事件 id。
    :returns: EventLog row。
    :raises HostDurableError: row 不存在时抛出。
    """

    row = event_log_store.read_event_by_id(transaction, event_id)
    if row is None:
        raise HostDurableError("accepted tool fact event is missing")
    return row


def _ack_result_digest(candidate: ToolFactAcceptCandidate) -> str:
    """返回 accepted ack 的 result digest。

    :param candidate: 工具事实候选。
    :returns: outcome digest，reuse 无 outcome 时回退 semantic input digest。
    """

    if candidate.result is not None:
        return candidate.result.outcome_digest
    return candidate.idempotency.semantic_input_digest


def _idempotency_record_ref(record: IdempotencyRecord) -> str:
    """构造稳定幂等记录引用。

    :param record: 幂等记录。
    :returns: 幂等记录引用文本。
    """

    return (
        f"{record.scope_kind}:{record.scope_id}:"
        f"{record.idempotency_key}"
    )


def _rejected_ack(
    candidate: ToolFactAcceptCandidate,
    reason_code: ToolAcceptRejectReason,
    message: str,
    *,
    retryable: bool,
) -> ToolFactRejectedAck:
    """构造 rejected ack。

    :param candidate: 工具事实候选。
    :param reason_code: 拒绝原因码。
    :param message: 诊断说明。
    :param retryable: 是否可重试。
    :returns: rejected ack。
    """

    return ToolFactRejectedAck(
        reason_code=reason_code,
        message=message,
        diagnostic_refs=candidate.diagnostics.diagnostic_refs,
        retryable=retryable,
    )


def _event_ref_from_row(row: EventLogRow) -> HostEventRef:
    """从 EventLog row 构造事件引用。

    :param row: EventLog row。
    :returns: HostEventRef。
    """

    return HostEventRef(event_id=row.event_id, event_sequence=row.event_sequence)


def _event_ref_json(ref: HostEventRef) -> JsonValue:
    """把事件引用投影为 JSON。

    :param ref: Host event ref。
    :returns: JSON mapping。
    """

    return {"event_id": ref.event_id, "event_sequence": ref.event_sequence}


def _payload_ref_json(ref: HostPayloadRef | None) -> JsonValue:
    """把 payload ref 投影为 JSON。

    :param ref: payload ref；无则为 ``None``。
    :returns: JSON 值。
    """

    if ref is None:
        return None
    return {"payload_ref": ref.payload_ref, "payload_digest": ref.payload_digest}


def _duplicate_scope_json(scope: DuplicateGovernanceScope | None) -> JsonValue:
    """把 duplicate governance scope 投影为 JSON。

    :param scope: duplicate governance scope；无则为 ``None``。
    :returns: JSON 值。
    """

    if scope is None:
        return None
    return {"kind": scope.kind, "attempt_id": scope.attempt_id}


def _truncation_json(fact: ToolTruncationFact | None) -> JsonValue:
    """把截断事实投影为 JSON。

    :param fact: 截断事实；无则为 ``None``。
    :returns: JSON 值。
    """

    if fact is None:
        return None
    return {
        "applied": fact.applied,
        "strategy": fact.strategy,
        "original_digest": fact.original_digest,
        "truncated_digest": fact.truncated_digest,
        "cursor_hint": fact.cursor_hint,
    }


def _policy_decision_json(decision: ToolPolicyDecision) -> JsonValue:
    """把 policy decision 投影为 JSON。

    :param decision: policy decision。
    :returns: JSON mapping。
    """

    return {
        "kind": decision.kind.value,
        "reason_code": decision.reason_code,
        "message": decision.message,
    }


def _policy_reason_json(decision: ToolPolicyDecision) -> JsonValue:
    """构造 EventLog 顶层 reason JSON。

    :param decision: policy decision。
    :returns: reason JSON。
    """

    return {"reason": decision.reason_code or decision.kind.value}


def _diagnostic_ref_json(ref: ToolTraceDiagnosticRef) -> JsonValue:
    """把诊断引用投影为 JSON。

    :param ref: 诊断引用。
    :returns: JSON mapping。
    """

    return {"ref_id": ref.ref_id}


def _validate_tool_accept_identity(identity: ToolAcceptIdentity) -> None:
    """校验工具事实 accept identity 子结构内部字段。

    :param identity: 待校验的执行身份子结构。
    :returns: ``None``。
    :raises ValueError: 任一 identity 字段为空时抛出。
    """

    for field_name, value in (
        ("session_id", identity.session_id),
        ("run_id", identity.run_id),
        ("attempt_id", identity.attempt_id),
        ("execution_id", identity.execution_id),
    ):
        _require_non_empty_text(value, field_name=field_name)


def _validate_tool_accept_call(call: ToolAcceptCall) -> None:
    """校验工具事实 accept call 子结构内部字段。

    :param call: 待校验的工具调用子结构。
    :returns: ``None``。
    :raises ValueError: 文本字段为空或 digest 非法时抛出。
    """

    for field_name, value in (
        ("iteration_id", call.iteration_id),
        ("tool_call_id", call.tool_call_id),
        ("tool_name", call.tool_name),
    ):
        _require_non_empty_text(value, field_name=field_name)
    _require_sha256_digest(
        call.tool_schema_digest, field_name="tool_schema_digest"
    )
    _require_sha256_digest(
        call.tool_identity_digest, field_name="tool_identity_digest"
    )
    _require_sha256_digest(
        call.normalized_arguments_digest,
        field_name="normalized_arguments_digest",
    )
    if call.accepted_arguments is not None:
        _validate_json_mapping(
            call.accepted_arguments, field_name="accepted_arguments"
        )
        expected_arguments_digest = _accepted_arguments_digest(
            call.accepted_arguments
        )
        if call.normalized_arguments_digest != expected_arguments_digest:
            raise ValueError(
                "normalized_arguments_digest must match accepted canonical arguments"
            )
    _require_optional_non_empty_text(
        call.semantic_query_text, field_name="semantic_query_text"
    )


def _validate_tool_accept_result(result: ToolAcceptResult) -> None:
    """校验工具事实 accept result 子结构内部字段。

    :param result: 待校验的工具结果子结构。
    :returns: ``None``。
    :raises ValueError: digest、payload ref、截断事实、timing signal 或失败
        metadata 非法时抛出。
    """

    _require_sha256_digest(result.outcome_digest, field_name="outcome_digest")
    _require_optional_sha256_digest(
        result.payload_digest, field_name="payload_digest"
    )
    if (
        result.payload_ref is not None
        and result.payload_digest != result.payload_ref.payload_digest
    ):
        raise ValueError("payload_digest must match payload_ref digest")
    if result.truncation is not None and not isinstance(
        result.truncation, ToolTruncationFact
    ):
        raise ValueError("truncation must be ToolTruncationFact")
    _validate_tool_timing_signal(result.tool_timing)
    _validate_failure_metadata_signal(result.failure_metadata)


def _validate_tool_timing_signal(signal: Mapping[str, JsonValue]) -> None:
    """校验 ToolRuntime 生成的工具耗时 signal。

    :param signal: tool_timing JSON object。
    :returns: ``None``。
    :raises ValueError: 必填字段缺失、字段类型非法或 duration 为负时抛出。
    """

    if not isinstance(signal, Mapping):
        raise ValueError("tool_timing must be JSON object")
    schema_version = signal.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != _TOOL_TIMING_SCHEMA_VERSION
    ):
        raise ValueError("tool_timing.schema_version must be 1")
    status = signal.get("status")
    if status == _TOOL_TIMING_STATUS_AVAILABLE:
        _require_signal_text(signal, "started_at")
        _require_signal_text(signal, "finished_at")
        duration_ms = signal.get("duration_ms")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0
        ):
            raise ValueError("tool_timing.duration_ms must be non-negative integer")
        if signal.get("duration_source") != _TOOL_TIMING_DURATION_SOURCE_META:
            raise ValueError("tool_timing.duration_source must be tool_result_meta")
        return
    if status == _TOOL_TIMING_STATUS_MISSING_META:
        for field_name in ("started_at", "finished_at", "duration_ms"):
            if signal.get(field_name) is not None:
                raise ValueError(f"tool_timing.{field_name} must be null")
        if signal.get("duration_source") is not None:
            raise ValueError("tool_timing.duration_source must be null")
        return
    raise ValueError("tool_timing.status is unsupported")


def _require_signal_text(signal: Mapping[str, JsonValue], field_name: str) -> str:
    """读取 timing signal 的必填文本字段。

    :param signal: tool_timing JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises ValueError: 字段缺失或不是非空文本时抛出。
    """

    value = signal.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise ValueError(f"tool_timing.{field_name} must be text")


def _validate_failure_metadata_signal(
    signal: Mapping[str, JsonValue] | None,
) -> None:
    """校验 ToolRuntime 生成的失败元数据 signal。

    :param signal: failure metadata JSON object；成功工具结果为 ``None``。
    :returns: ``None``。
    :raises ValueError: 必填字段缺失、字段类型非法或闭集枚举非法时抛出。
    """

    if signal is None:
        return
    if not isinstance(signal, Mapping):
        raise ValueError("failure_metadata must be JSON object or null")
    if signal.get("schema_version") != _FAILURE_METADATA_SCHEMA_VERSION:
        raise ValueError("failure_metadata.schema_version must be 1")
    if signal.get("signal_source") != _FAILURE_SIGNAL_SOURCE_TOOL_RESULT_ACCEPTED:
        raise ValueError("failure_metadata.signal_source is unsupported")
    failure_kind = signal.get("failure_kind")
    if failure_kind == _FAILURE_KIND_TOOL_FAILED:
        _require_failure_signal_text(signal, "error_code")
        _validate_bounded_text_fields(signal, "repair_hint")
        _validate_failure_diagnostic_refs(signal)
        return
    if failure_kind == _FAILURE_KIND_TOOL_CANCELLED:
        _require_failure_signal_text(signal, "cancel_reason")
        _validate_bounded_text_fields(signal, "cancel_message")
        _validate_bounded_text_fields(signal, "cancel_hint")
        _validate_failure_diagnostic_refs(signal)
        return
    if failure_kind == _FAILURE_KIND_POLICY_BLOCKED:
        _require_failure_signal_text(signal, "policy_decision_kind")
        _require_failure_signal_text(signal, "policy_block_reason")
        _validate_failure_diagnostic_refs(signal)
        return
    raise ValueError("failure_metadata.failure_kind is unsupported")


def _validate_candidate_failure_metadata(
    candidate: ToolFactAcceptCandidate, *, expected_kind: str | None
) -> None:
    """校验 candidate fact kind 与 failure metadata 的一致性。

    :param candidate: 工具事实候选。
    :param expected_kind: 期望的 failure kind；成功结果为 ``None``。
    :returns: ``None``。
    :raises ValueError: metadata 缺失、额外存在或 kind 不匹配时抛出。
    """

    metadata = _candidate_result(candidate).failure_metadata
    if expected_kind is None:
        if metadata is not None:
            raise ValueError("completed result requires failure_metadata=null")
        return
    if metadata is None:
        raise ValueError(f"{candidate.tool_fact_kind.value} requires failure_metadata")
    failure_kind = metadata.get("failure_kind")
    if failure_kind != expected_kind:
        raise ValueError(
            f"{candidate.tool_fact_kind.value} failure_metadata kind mismatch"
        )


def _require_failure_signal_text(
    signal: Mapping[str, JsonValue], field_name: str
) -> str:
    """读取 failure metadata 的必填文本字段。

    :param signal: failure metadata JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises ValueError: 字段缺失或不是非空文本时抛出。
    """

    value = signal.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise ValueError(f"failure_metadata.{field_name} must be text")


def _validate_bounded_text_fields(
    signal: Mapping[str, JsonValue], field_name: str
) -> None:
    """校验 bounded text 三字段组合。

    :param signal: failure metadata JSON object。
    :param field_name: bounded text 字段名前缀。
    :returns: ``None``。
    :raises ValueError: bounded 文本、digest 或 truncated 字段组合非法时抛出。
    """

    value = signal.get(field_name)
    digest = signal.get(f"{field_name}_sha256")
    truncated = signal.get(f"{field_name}_truncated")
    if not isinstance(truncated, bool):
        raise ValueError(f"failure_metadata.{field_name}_truncated must be bool")
    if value is None:
        if digest is not None or truncated:
            raise ValueError(f"failure_metadata.{field_name} null fields are invalid")
        return
    if not isinstance(value, str):
        raise ValueError(f"failure_metadata.{field_name} must be text or null")
    if len(value) > _TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS:
        raise ValueError(f"failure_metadata.{field_name} exceeds bounded limit")
    if not isinstance(digest, str) or not is_sha256_digest(digest):
        raise ValueError(f"failure_metadata.{field_name}_sha256 must be sha256 digest")


def _validate_failure_diagnostic_refs(signal: Mapping[str, JsonValue]) -> None:
    """校验 failure metadata diagnostic refs。

    :param signal: failure metadata JSON object。
    :returns: ``None``。
    :raises ValueError: refs 字段不是文本数组时抛出。
    """

    refs = signal.get("diagnostic_refs")
    if not isinstance(refs, list):
        raise ValueError("failure_metadata.diagnostic_refs must be JSON array")
    for ref in refs:
        if not isinstance(ref, str) or ref.strip() == "":
            raise ValueError("failure_metadata.diagnostic_refs must contain text")


def _validate_tool_accept_duplicate_governance(
    duplicate: ToolAcceptDuplicateGovernance,
) -> None:
    """校验工具事实 accept duplicate governance 子结构内部字段。

    :param duplicate: 待校验的 duplicate governance 子结构。
    :returns: ``None``。
    :raises ValueError: duplicate 决策、key、scope、message 或 prior refs 非法时抛出。
    """

    _require_optional_non_empty_text(
        duplicate.duplicate_key, field_name="duplicate_key"
    )
    _require_optional_non_empty_text(
        duplicate.duplicate_decision_message,
        field_name="duplicate_decision_message",
    )
    if not isinstance(duplicate.duplicate_decision, DuplicateDecisionKind):
        raise ValueError("duplicate_decision must be DuplicateDecisionKind")
    if duplicate.duplicate_scope is not None and not isinstance(
        duplicate.duplicate_scope, DuplicateGovernanceScope
    ):
        raise ValueError("duplicate_scope must be DuplicateGovernanceScope")
    if duplicate.duplicate_decision in (
        DuplicateDecisionKind.REUSE,
        DuplicateDecisionKind.HINT,
        DuplicateDecisionKind.REQUIRE_JUSTIFICATION,
        DuplicateDecisionKind.HARD_STOP,
        DuplicateDecisionKind.DURABLE_MISSING,
    ):
        if duplicate.duplicate_key is None:
            raise ValueError("duplicate decision requires duplicate_key")
    if duplicate.duplicate_scope is None:
        raise ValueError("duplicate decision requires duplicate_scope")
    if duplicate.duplicate_decision_message is None:
        raise ValueError("duplicate decision requires duplicate_decision_message")
    for prior_ref in duplicate.reuse_prior_event_refs:
        if not isinstance(prior_ref, HostEventRef):
            raise ValueError("reuse_prior_event_refs must contain HostEventRef")


def _validate_tool_accept_governance(governance: ToolAcceptGovernance) -> None:
    """校验工具事实 accept governance 子结构内部字段。

    :param governance: 待校验的治理子结构。
    :returns: ``None``。
    :raises ValueError: policy、工具幂等 key 或 duplicate governance 非法时抛出。
    """

    if not isinstance(governance.policy_decision, ToolPolicyDecision):
        raise ValueError("policy_decision must be ToolPolicyDecision")
    _validate_policy_decision_fields(governance.policy_decision)
    _require_optional_non_empty_text(
        governance.tool_idempotency_key, field_name="tool_idempotency_key"
    )
    if governance.duplicate is not None and not isinstance(
        governance.duplicate, ToolAcceptDuplicateGovernance
    ):
        raise ValueError("duplicate must be ToolAcceptDuplicateGovernance")


def _validate_tool_accept_idempotency(idempotency: ToolAcceptIdempotency) -> None:
    """校验工具事实 accept idempotency 子结构内部字段。

    :param idempotency: 待校验的幂等子结构。
    :returns: ``None``。
    :raises ValueError: 幂等 key 为空或 semantic input digest 非法时抛出。
    """

    _require_non_empty_text(
        idempotency.accept_idempotency_key,
        field_name="accept_idempotency_key",
    )
    _require_sha256_digest(
        idempotency.semantic_input_digest,
        field_name="semantic_input_digest",
    )


def _validate_tool_accept_diagnostics(diagnostics: ToolAcceptDiagnostics) -> None:
    """校验工具事实 accept diagnostics 子结构内部字段。

    :param diagnostics: 待校验的诊断子结构。
    :returns: ``None``。
    :raises ValueError: 任一诊断引用类型非法时抛出。
    """

    for ref in diagnostics.diagnostic_refs:
        if not isinstance(ref, ToolTraceDiagnosticRef):
            raise ValueError("diagnostic_refs must contain ToolTraceDiagnosticRef")


def _validate_common_candidate_fields(candidate: ToolFactAcceptCandidate) -> None:
    """校验 candidate 所有 fact kind 共享的必填字段。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: 字段缺失或 digest 非法时抛出。
    """

    if not isinstance(candidate.identity, ToolAcceptIdentity):
        raise ValueError("identity must be ToolAcceptIdentity")
    if not isinstance(candidate.call, ToolAcceptCall):
        raise ValueError("call must be ToolAcceptCall")
    if candidate.result is not None and not isinstance(
        candidate.result, ToolAcceptResult
    ):
        raise ValueError("result must be ToolAcceptResult")
    if not isinstance(candidate.governance, ToolAcceptGovernance):
        raise ValueError("governance must be ToolAcceptGovernance")
    if not isinstance(candidate.idempotency, ToolAcceptIdempotency):
        raise ValueError("idempotency must be ToolAcceptIdempotency")
    if not isinstance(candidate.diagnostics, ToolAcceptDiagnostics):
        raise ValueError("diagnostics must be ToolAcceptDiagnostics")
    if not isinstance(candidate.tool_fact_kind, ToolFactKind):
        raise ValueError("tool_fact_kind must be ToolFactKind")


def _validate_duplicate_fields(candidate: ToolFactAcceptCandidate) -> None:
    """校验 duplicate governance 字段组合。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: duplicate decision 与 duplicate key 组合非法时抛出。
    """

    duplicate = candidate.governance.duplicate
    if duplicate is None:
        return
    _validate_tool_accept_duplicate_governance(duplicate)


def _validate_policy_decision_fields(decision: ToolPolicyDecision) -> None:
    """校验工具治理决策字段组合。

    :param decision: 工具治理决策。
    :returns: ``None``。
    :raises ValueError: 决策类别或原因字段组合非法时抛出。
    """

    if not isinstance(decision.kind, ToolPolicyDecisionKind):
        raise ValueError("policy_decision.kind must be ToolPolicyDecisionKind")
    _require_optional_non_empty_text(
        decision.reason_code, field_name="policy_decision.reason_code"
    )
    _require_optional_non_empty_text(
        decision.message, field_name="policy_decision.message"
    )
    if decision.kind is ToolPolicyDecisionKind.ALLOW:
        if decision.reason_code is not None or decision.message is not None:
            raise ValueError("allow policy decision must not carry reason or message")
        return
    if decision.reason_code is None or decision.message is None:
        raise ValueError("governed policy decision requires reason and message")


def _validate_governed_error_candidate(candidate: ToolFactAcceptCandidate) -> None:
    """校验 governed error 工具事实候选。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: policy / duplicate 字段组合不符合 governed error
        语义时抛出。
    """

    policy_decision = candidate.governance.policy_decision
    if policy_decision.kind in (
        ToolPolicyDecisionKind.ALLOW,
        ToolPolicyDecisionKind.REUSE,
    ):
        raise ValueError("governed_error requires governed policy decision")
    if policy_decision.kind is ToolPolicyDecisionKind.GOVERNED_ERROR:
        if _candidate_reuse_prior_event_refs(candidate):
            raise ValueError("plain governed_error must not carry prior reuse refs")
        return
    _validate_duplicate_governed_candidate(candidate)


def _validate_duplicate_governed_candidate(
    candidate: ToolFactAcceptCandidate,
) -> None:
    """校验 duplicate 触发的 governed error 候选。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: duplicate 决策、prior refs 或 reason/message
        与 policy 决策不一致时抛出。
    """

    duplicate = candidate.governance.duplicate
    decision = duplicate.duplicate_decision if duplicate is not None else None
    if decision is DuplicateDecisionKind.DURABLE_MISSING:
        if _candidate_reuse_prior_event_refs(candidate):
            raise ValueError("durable-missing duplicate must not carry prior refs")
        expected_reason = _duplicate_reason_code(decision)
        if candidate.governance.policy_decision.reason_code != expected_reason:
            raise ValueError("durable-missing duplicate reason must match decision")
        return
    if decision is None or decision not in (
        DuplicateDecisionKind.HINT,
        DuplicateDecisionKind.REQUIRE_JUSTIFICATION,
        DuplicateDecisionKind.HARD_STOP,
    ):
        raise ValueError("duplicate governed error requires duplicate decision")
    if candidate.governance.policy_decision.kind.value != decision.value:
        raise ValueError("duplicate governed policy kind must match decision")
    if not _candidate_reuse_prior_event_refs(candidate):
        raise ValueError("duplicate governed error requires prior event refs")
    expected_reason = _duplicate_reason_code(decision)
    if candidate.governance.policy_decision.reason_code != expected_reason:
        raise ValueError("duplicate governed reason must match decision")
    if duplicate is None:
        raise ValueError("duplicate governed error requires duplicate decision")
    expected_message = duplicate.duplicate_decision_message
    if candidate.governance.policy_decision.message != expected_message:
        raise ValueError("duplicate governed message must match decision")


def _validate_result_fact_policy(candidate: ToolFactAcceptCandidate) -> None:
    """校验普通结果事实只携带 allow policy。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: 普通 completed / failed / cancelled fact 携带非
        allow policy 时抛出。
    """

    if candidate.result is None:
        raise ValueError(f"{candidate.tool_fact_kind.value} requires result")
    if candidate.governance.policy_decision.kind is not ToolPolicyDecisionKind.ALLOW:
        raise ValueError(f"{candidate.tool_fact_kind.value} requires allow policy")


def _validate_reuse_candidate(candidate: ToolFactAcceptCandidate) -> None:
    """校验 reuse 工具事实候选。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: reuse 字段不满足 canonical 语义时抛出。
    """

    duplicate = candidate.governance.duplicate
    if duplicate is None or duplicate.duplicate_key is None:
        raise ValueError("reuse requires duplicate_key")
    if duplicate.duplicate_decision is not DuplicateDecisionKind.REUSE:
        raise ValueError("reuse requires duplicate_decision=reuse")
    if candidate.governance.policy_decision.kind is not ToolPolicyDecisionKind.REUSE:
        raise ValueError("reuse requires policy_decision=reuse")
    if candidate.governance.policy_decision.reason_code != _duplicate_reason_code(
        DuplicateDecisionKind.REUSE
    ):
        raise ValueError("reuse reason must match duplicate decision")
    if duplicate.duplicate_decision_message is None:
        raise ValueError("reuse requires duplicate_decision_message")
    expected_message = duplicate.duplicate_decision_message
    if candidate.governance.policy_decision.message != expected_message:
        raise ValueError("reuse message must match duplicate decision")
    if not duplicate.reuse_prior_event_refs:
        raise ValueError("reuse requires prior event refs")
    if candidate.result is not None:
        raise ValueError("reuse must not carry result")


def _require_raw_tool_outcome(candidate: ToolFactAcceptCandidate) -> None:
    """校验非 reuse 工具事实携带 raw 工具 outcome。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: raw 工具 outcome 缺失时抛出。
    """

    if candidate.result is None:
        raise ValueError(f"{candidate.tool_fact_kind.value} requires result")
    if candidate.result.raw_tool_outcome is None:
        raise ValueError(f"{candidate.tool_fact_kind.value} requires raw_tool_outcome")


def _candidate_result(candidate: ToolFactAcceptCandidate) -> ToolAcceptResult:
    """返回非 reuse candidate 的 result 子结构。

    :param candidate: 工具事实候选。
    :returns: result 子结构。
    :raises ValueError: candidate 未携带 result 时抛出。
    """

    if candidate.result is None:
        raise ValueError(f"{candidate.tool_fact_kind.value} requires result")
    return candidate.result


def _candidate_reuse_prior_event_refs(
    candidate: ToolFactAcceptCandidate,
) -> tuple[HostEventRef, ...]:
    """返回 candidate duplicate governance 中的 prior event refs。

    :param candidate: 工具事实候选。
    :returns: prior event refs；无 duplicate governance 时为空元组。
    """

    duplicate = candidate.governance.duplicate
    if duplicate is None:
        return ()
    return duplicate.reuse_prior_event_refs


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验文本非空。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty_text(
    value: str | None, *, field_name: str
) -> None:
    """校验 optional 文本不为空白。

    :param value: 待校验文本；无值时为 ``None``。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空白时抛出。
    """

    if value is not None and value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty when provided")


def _validate_json_mapping(
    value: Mapping[str, JsonValue], *, field_name: str
) -> None:
    """递归校验 JSON object 参数映射。

    :param value: 待校验 JSON object。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises ValueError: key 为空或嵌套值不是 JSON 兼容结构时抛出。
    """

    for key, nested_value in value.items():
        if not isinstance(key, str) or key.strip() == "":
            raise ValueError(f"{field_name} keys must be non-empty")
        _validate_json_value(nested_value, field_name=f"{field_name}.{key}")


def _validate_json_value(value: JsonValue, *, field_name: str) -> None:
    """递归校验 JSON 值边界。

    :param value: 待校验 JSON 值。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises ValueError: 值不是 JSON 兼容结构时抛出。
    """

    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must be finite JSON number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, field_name=f"{field_name}[{index}]")
        return
    if isinstance(value, Mapping):
        _validate_json_mapping(
            cast(Mapping[str, JsonValue], value), field_name=field_name
        )
        return
    raise ValueError(f"{field_name} must be JSON-compatible")


def _require_sha256_digest(value: str | None, *, field_name: str) -> None:
    """校验必填 sha256 digest。

    :param value: digest 文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: digest 缺失或非法时抛出。
    """

    if value is None or not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_optional_sha256_digest(
    value: str | None, *, field_name: str
) -> None:
    """校验 optional sha256 digest。

    :param value: digest 文本；无值时为 ``None``。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: digest 非法时抛出。
    """

    if value is not None and not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be a sha256 digest when provided")


def _fetch_more_tool_definition(callable_: FetchMoreToolCallable) -> ToolDefinition:
    """构造内置 ``fetch_more`` framework tool 声明。

    :param callable_: 已创建的 ``fetch_more`` callable。
    :returns: framework tool 声明。
    """

    properties: dict[str, JsonValue] = {
        _FETCH_MORE_CURSOR_FIELD: {
            "type": "string",
            "description": (
                "上一条截断结果给出的 cursor 引用标签。必须原样使用；"
                "它只用于定位待续读内容，不是业务事实或推理依据。"
            ),
        },
        _FETCH_MORE_SCOPE_TOKEN_FIELD: {
            "type": "string",
            "description": (
                "上一条截断结果给出的 scope_token 引用标签。必须原样使用；"
                "它只用于校验本次续读范围，不是业务事实或推理依据。"
            ),
        },
        _FETCH_MORE_LIMIT_FIELD: {
            "type": "integer",
            "minimum": 1,
            "description": (
                "可选的本次补读单位数，必须是正整数；"
                "省略时由系统使用当前续读上限。"
            ),
        },
    }
    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name=FrameworkToolName.FETCH_MORE.value,
            description=_FETCH_MORE_DESCRIPTION,
            parameters=ToolParametersSchema(
                type="object",
                properties=properties,
                required=(
                    _FETCH_MORE_CURSOR_FIELD,
                    _FETCH_MORE_SCOPE_TOKEN_FIELD,
                ),
                additional_properties=False,
            ),
        ),
    )
    return ToolDefinition(
        name=FrameworkToolName.FETCH_MORE.value,
        schema=schema,
        callable=callable_,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=("framework",),
    )


def _fetch_more_request_from_call(
    call: ToolCallRequest,
) -> FetchMoreRequest | ToolFailedOutcome:
    """从工具调用参数解析 ``FetchMoreRequest``。

    :param call: ``fetch_more`` 工具调用。
    :returns: 解析后的请求；参数非法时返回普通失败 outcome。
    """

    cursor = call.arguments.get(_FETCH_MORE_CURSOR_FIELD)
    scope_token = call.arguments.get(_FETCH_MORE_SCOPE_TOKEN_FIELD)
    limit_value = call.arguments.get(_FETCH_MORE_LIMIT_FIELD)
    if not isinstance(cursor, str) or not isinstance(scope_token, str):
        return _truncation_failure(
            "fetch_more requires cursor and scope_token string arguments",
        )
    limit: int | None = None
    if limit_value is not None:
        if isinstance(limit_value, bool) or not isinstance(limit_value, int):
            return _truncation_failure(
                "fetch_more limit must be a positive integer",
            )
        limit = limit_value
    try:
        return FetchMoreRequest(
            cursor=cursor,
            scope_token=scope_token,
            limit=limit,
        )
    except ValueError as exc:
        return _truncation_failure(str(exc))


def _tool_truncation_strategy(
    spec: ToolTruncateSpec,
) -> ToolTruncationStrategy | None:
    """读取截断声明策略。

    :param spec: 截断声明。
    :returns: 已启用的截断策略；未声明时为 ``None``。
    """

    return spec.strategy


def _select_truncation_value(
    value: JsonValue, spec: ToolTruncateSpec
) -> _SelectedTruncationValue | None:
    """按截断声明选择目标 JSON 值。

    :param value: 工具 completed payload。
    :param spec: 截断声明。
    :returns: 目标值；无法选择时为 ``None``。
    """

    if spec.field_path is not None:
        selected = _value_at_path(value, spec.field_path)
        if selected is None:
            return None
        return _SelectedTruncationValue(value=selected)
    if spec.target_field is not None:
        if not isinstance(value, Mapping):
            return None
        selected = value.get(spec.target_field)
        if selected is None:
            return None
        return _SelectedTruncationValue(value=selected)
    return _SelectedTruncationValue(value=value)


def _value_at_path(value: JsonValue, path: tuple[str, ...]) -> JsonValue | None:
    """读取嵌套 mapping 路径上的 JSON 值。

    :param value: 根 JSON 值。
    :param path: 字段路径。
    :returns: 路径值；不存在时为 ``None``。
    """

    current = value
    for item in path:
        if not isinstance(current, Mapping):
            return None
        next_value = current.get(item)
        if next_value is None:
            return None
        current = next_value
    return current


def _replace_truncation_value(
    value: JsonValue, spec: ToolTruncateSpec, replacement: JsonValue
) -> JsonValue | None:
    """把截断后的公开值写回工具 payload。

    :param value: 原始工具 payload。
    :param spec: 截断声明。
    :param replacement: 替换值。
    :returns: 新 payload；无法替换时为 ``None``。
    """

    if spec.field_path is not None:
        return _replace_value_at_path(value, spec.field_path, replacement)
    if spec.target_field is not None:
        if not isinstance(value, Mapping):
            return None
        result: dict[str, JsonValue] = dict(value)
        result[spec.target_field] = replacement
        return result
    return replacement


def _replace_value_at_path(
    value: JsonValue, path: tuple[str, ...], replacement: JsonValue
) -> JsonValue | None:
    """替换嵌套 mapping 路径上的 JSON 值。

    :param value: 根 JSON 值。
    :param path: 字段路径。
    :param replacement: 替换值。
    :returns: 新 JSON 值；无法替换时为 ``None``。
    """

    if not path:
        return replacement
    if not isinstance(value, Mapping):
        return None
    head = path[0]
    child = value.get(head)
    if child is None:
        return None
    replaced_child = _replace_value_at_path(child, path[1:], replacement)
    if replaced_child is None:
        return None
    result: dict[str, JsonValue] = dict(value)
    result[head] = replaced_child
    return result


def _truncated_value_for_strategy(
    *,
    strategy: ToolTruncationStrategy,
    value: JsonValue,
    spec: ToolTruncateSpec,
) -> _CreatedTruncation | None:
    """按策略截断 JSON 值并构造剩余引用。

    :param strategy: 截断策略。
    :param value: 待截断值。
    :param spec: 截断声明。
    :returns: 截断结果；无需截断或不支持时为 ``None``。
    """

    if strategy is ToolTruncationStrategy.TEXT_CHARS:
        return _truncate_text_chars(value, spec)
    if strategy is ToolTruncationStrategy.TEXT_LINES:
        return _truncate_text_lines(value, spec)
    if strategy is ToolTruncationStrategy.LIST_ITEMS:
        return _truncate_list_items(value, spec)
    if strategy is ToolTruncationStrategy.BINARY_BYTES:
        return _truncate_binary_bytes(value, spec)
    return None


def _truncate_text_chars(
    value: JsonValue, spec: ToolTruncateSpec
) -> _CreatedTruncation | None:
    """按字符数截断文本。

    :param value: 待截断值。
    :param spec: 截断声明。
    :returns: 截断结果；无需截断时为 ``None``。
    """

    if not isinstance(value, str):
        return None
    limit = _positive_limit(spec, _TEXT_CHARS_LIMIT_KEY)
    if limit is None or len(value) <= limit:
        return None
    visible = value[:limit]
    remaining = value[limit:]
    return _CreatedTruncation(
        visible_value=visible,
        remaining_ref=TextCharsRemainderRef(
            remaining_text=remaining,
            digest=sha256_digest_json({"remaining_text": remaining}),
        ),
    )


def _truncate_text_lines(
    value: JsonValue, spec: ToolTruncateSpec
) -> _CreatedTruncation | None:
    """按行数截断文本。

    :param value: 待截断值。
    :param spec: 截断声明。
    :returns: 截断结果；无需截断时为 ``None``。
    """

    if not isinstance(value, str):
        return None
    limit = _positive_limit(spec, _TEXT_LINES_LIMIT_KEY)
    lines = value.splitlines()
    if limit is None or len(lines) <= limit:
        return None
    visible = "\n".join(lines[:limit])
    remaining = tuple(lines[limit:])
    return _CreatedTruncation(
        visible_value=visible,
        remaining_ref=TextLinesRemainderRef(
            remaining_lines=remaining,
            digest=sha256_digest_json({"remaining_lines": list(remaining)}),
        ),
    )


def _truncate_list_items(
    value: JsonValue, spec: ToolTruncateSpec
) -> _CreatedTruncation | None:
    """按列表项数截断 JSON 数组。

    :param value: 待截断值。
    :param spec: 截断声明。
    :returns: 截断结果；无需截断时为 ``None``。
    """

    if not isinstance(value, list):
        return None
    limit = _positive_limit(spec, _LIST_ITEMS_LIMIT_KEY)
    if limit is None or len(value) <= limit:
        return None
    visible = value[:limit]
    remaining = tuple(value[limit:])
    return _CreatedTruncation(
        visible_value=visible,
        remaining_ref=ListItemsRemainderRef(
            remaining_items=remaining,
            digest=sha256_digest_json({"remaining_items": list(remaining)}),
        ),
    )


def _truncate_binary_bytes(
    value: JsonValue, spec: ToolTruncateSpec
) -> _CreatedTruncation | None:
    """按原始字节数截断 base64 字符串。

    :param value: base64 ASCII 字符串。
    :param spec: 截断声明。
    :returns: 截断结果；无需截断或解码失败时为 ``None``。
    """

    if not isinstance(value, str):
        return None
    limit = _positive_limit(spec, _BINARY_BYTES_LIMIT_KEY)
    if limit is None:
        return None
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return None
    if len(raw) <= limit:
        return None
    visible = base64.b64encode(raw[:limit]).decode("ascii")
    remaining = raw[limit:]
    return _CreatedTruncation(
        visible_value=visible,
        remaining_ref=BinaryBytesRemainderRef(
            remaining_bytes=remaining,
            digest=sha256_digest_json(
                {"remaining_bytes_base64": base64.b64encode(remaining).decode("ascii")}
            ),
        ),
    )


def _positive_limit(spec: ToolTruncateSpec, key: str) -> int | None:
    """读取正整数截断上限。

    :param spec: 截断声明。
    :param key: limit key。
    :returns: 正整数上限；缺失或非法时为 ``None``。
    """

    value = spec.limits.get(key)
    if value is None or value < _MIN_TRUNCATION_LIMIT:
        return None
    return value


def _truncated_public_value(
    *, visible_value: JsonValue, cursor_id: str, scope_token: str
) -> JsonValue:
    """构造 LLM-facing 截断值。

    :param visible_value: 已截断的可见值。
    :param cursor_id: 不透明 cursor。
    :param scope_token: scope token。
    :returns: JSON 对象，不包含任何内部剩余内容。
    """

    return {
        _TRUNCATED_APPLIED_FIELD: True,
        _TRUNCATED_VALUE_FIELD: visible_value,
        _TRUNCATED_META_FIELD: {
            _FETCH_MORE_CURSOR_FIELD: cursor_id,
            _FETCH_MORE_SCOPE_TOKEN_FIELD: scope_token,
        },
    }


def _scope_token_digest(scope_token: str) -> str:
    """计算 scope token digest。

    :param scope_token: 明文 scope token。
    :returns: Host canonical sha256 digest。
    """

    return sha256_digest_json({"scope_token": scope_token})


def _fetch_more_value(
    remainder: TruncatedRemainderRef, limit: int | None
) -> JsonValue | None:
    """从剩余引用读取公开补读值。

    :param remainder: 剩余内容引用。
    :param limit: 可选补读上限。
    :returns: 可返回给 LLM 的 JSON 值；摘要不匹配时为 ``None``。
    """

    if not _remainder_digest_matches(remainder):
        return None
    if isinstance(remainder, TextCharsRemainderRef):
        return remainder.remaining_text if limit is None else remainder.remaining_text[:limit]
    if isinstance(remainder, TextLinesRemainderRef):
        lines = remainder.remaining_lines if limit is None else remainder.remaining_lines[:limit]
        return "\n".join(lines)
    if isinstance(remainder, ListItemsRemainderRef):
        items = remainder.remaining_items if limit is None else remainder.remaining_items[:limit]
        return list(items)
    if isinstance(remainder, BinaryBytesRemainderRef):
        data = remainder.remaining_bytes if limit is None else remainder.remaining_bytes[:limit]
        return base64.b64encode(data).decode("ascii")
    return None


def _remainder_digest_matches(remainder: TruncatedRemainderRef) -> bool:
    """校验剩余内容引用 digest。

    :param remainder: 剩余内容引用。
    :returns: digest 匹配时返回 ``True``。
    """

    if isinstance(remainder, TextCharsRemainderRef):
        return remainder.digest == sha256_digest_json(
            {"remaining_text": remainder.remaining_text}
        )
    if isinstance(remainder, TextLinesRemainderRef):
        return remainder.digest == sha256_digest_json(
            {"remaining_lines": list(remainder.remaining_lines)}
        )
    if isinstance(remainder, ListItemsRemainderRef):
        return remainder.digest == sha256_digest_json(
            {"remaining_items": list(remainder.remaining_items)}
        )
    if isinstance(remainder, BinaryBytesRemainderRef):
        return remainder.digest == sha256_digest_json(
            {
                "remaining_bytes_base64": base64.b64encode(
                    remainder.remaining_bytes
                ).decode("ascii")
            }
        )
    return False


def _request_context_matches_scope(
    context: BatchToolExecutionContext, scope: ToolRuntimeExecutionScope
) -> bool:
    """判断批式工具上下文是否属于当前 ToolRuntime scope。

    :param context: 批式工具执行上下文。
    :param scope: ToolRuntime 执行 scope。
    :returns: session / run 匹配时返回 ``True``。
    """

    return context.session_id == scope.session_id and context.run_id == scope.run_id


def _normalized_arguments_digest(call: ToolCallRequest) -> str:
    """计算工具参数规范化 digest。

    :param call: 单次工具调用请求。
    :returns: Host canonical sha256 digest。
    """

    return _accepted_arguments_digest(call.arguments)


def _accepted_arguments_json(
    arguments: Mapping[str, JsonValue]
) -> Mapping[str, JsonValue]:
    """构造 accepted arguments 的 canonical JSON preimage。

    :param arguments: 已接受的工具参数映射。
    :returns: 与 ``normalized_arguments_digest`` 同源的 canonical JSON object。
    """

    return {"arguments": dict(arguments)}


def _accepted_arguments_digest(arguments: Mapping[str, JsonValue]) -> str:
    """计算 accepted canonical arguments JSON digest。

    :param arguments: 已接受的工具参数映射。
    :returns: 与 ``normalized_arguments_digest`` 同源的 sha256 digest。
    """

    return sha256_digest_json(_accepted_arguments_json(arguments))


def _required_accepted_arguments(
    call: ToolAcceptCall,
) -> Mapping[str, JsonValue]:
    """读取写入 accepted fact 必需的工具参数。

    :param call: 工具 accept call 子结构。
    :returns: accepted arguments 映射。
    :raises HostPayloadReferenceError: 参数 atom 缺失时抛出。
    """

    if call.accepted_arguments is None:
        raise HostPayloadReferenceError("tool call accepted arguments are missing")
    return call.accepted_arguments


def _tool_idempotency_key(
    call: ToolCallRequest, rule: ToolRuntimeToolPolicy
) -> str | None:
    """按 Host policy 从工具参数中提取工具级幂等 key。

    :param call: 单次工具调用请求。
    :param rule: 单工具 policy。
    :returns: 幂等 key；未配置或参数不是非空字符串时为 ``None``。
    """

    argument_name = rule.idempotency_key_argument_name
    if argument_name is None:
        return None
    value = call.arguments.get(argument_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _semantic_duplicate_key(
    call: ToolCallRequest, rule: ToolRuntimeToolPolicy
) -> str | None:
    """从工具参数中读取可选 semantic duplicate key。

    :param call: 单次工具调用请求。
    :param rule: 单工具 policy。
    :returns: semantic duplicate key；未配置或参数不是非空字符串时为 ``None``。
    """

    argument_name = rule.semantic_duplicate_key_argument_name
    if argument_name is None:
        return None
    value = call.arguments.get(argument_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _policy_decision_from_duplicate(
    decision: DuplicateDecision,
) -> ToolPolicyDecision:
    """把 duplicate decision 映射为 ToolRuntime policy decision。

    :param decision: duplicate governance 决策。
    :returns: 对应 policy decision。
    """

    reason_code = decision.reason_code or _duplicate_reason_code(decision.kind)
    if decision.message is None:
        raise ValueError("duplicate decision requires message")
    if decision.kind is DuplicateDecisionKind.DURABLE_MISSING:
        return ToolPolicyDecision(
            kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
            reason_code=reason_code,
            message=decision.message,
        )
    return ToolPolicyDecision(
        kind=ToolPolicyDecisionKind(decision.kind.value),
        reason_code=reason_code,
        message=decision.message,
    )


def _durable_missing_reason_for_policy(
    decision: ToolPolicyDecision,
) -> DuplicateDurableMissingReason:
    """根据 ToolRuntime bounded policy 决策推导 durable missing 原因。

    :param decision: ToolRuntime 生成的治理决策。
    :returns: duplicate owner 未产生 accepted fact 的原因。
    """

    if decision.reason_code == _TOOL_RUNTIME_CANCELLED_REASON:
        return DuplicateDurableMissingReason.OWNER_CANCELLED
    return DuplicateDurableMissingReason.GOVERNED_BEFORE_ACCEPT


def _durable_missing_reason_for_accept_result(
    result: ToolFactRejectedAck | ToolFactAcceptTimedOut,
) -> DuplicateDurableMissingReason:
    """根据 Host accept 结果推导 durable missing 原因。

    :param result: Host accept rejected 或 timed out 结果。
    :returns: duplicate owner 未产生 accepted fact 的原因。
    """

    if isinstance(result, ToolFactRejectedAck):
        return DuplicateDurableMissingReason.HOST_ACCEPT_REJECTED
    return DuplicateDurableMissingReason.HOST_ACCEPT_TIMEOUT


def _durable_missing_reason_for_awaiting_accept_result(
    result: ToolAwaitingRejectedAck | ToolAwaitingAcceptTimedOut,
) -> DuplicateDurableMissingReason:
    """根据 Host awaiting accept 结果推导 durable missing 原因。

    :param result: Host awaiting accept rejected 或 timed out 结果。
    :returns: duplicate owner 未产生 accepted awaiting marker 的原因。
    """

    if isinstance(result, ToolAwaitingRejectedAck):
        return DuplicateDurableMissingReason.HOST_ACCEPT_REJECTED
    return DuplicateDurableMissingReason.HOST_ACCEPT_TIMEOUT


def _is_runtime_dispatch_exception_outcome(outcome: ToolExecutionOutcome) -> bool:
    """判断 outcome 是否来自工具 dispatch / capsule 构造异常。

    :param outcome: 工具执行 outcome。
    :returns: dispatch 或 capsule 构造异常被 ToolRuntime 归一化时返回 ``True``。
    """

    return (
        isinstance(outcome, ToolFailedOutcome)
        and outcome.result.error
        in {
            _TOOL_RUNTIME_CALLABLE_FAILED_ERROR,
            _TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR,
        }
    )


def _tool_outcome_from_process_envelope(envelope: JsonValue) -> ToolExecutionOutcome:
    """把 process-backed 子进程 JSON 信封解析为工具 outcome。

    只有 ``completed`` 与 ``failed`` 是子进程允许表达的业务结果；未知、
    malformed、awaiting、cancelled、timeout 与 host_cancelled 信封均
    fail closed。父进程 cancel / timeout 由 Host capsule 外层独占治理。

    :param envelope: 子进程返回的 JSON 值。
    :returns: 工具 outcome。
    :raises Exception: 不主动抛出异常。
    """

    parsed = parse_process_tool_envelope(envelope)
    if isinstance(parsed, ProcessToolCompletedEnvelope):
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=parsed.value,
                meta=None,
            )
        )
    if isinstance(parsed, ProcessToolFailedEnvelope):
        return _tool_failed_outcome(
            error=parsed.error_type,
            message=parsed.message,
            hint=parsed.hint,
        )
    if isinstance(parsed, ProcessToolMalformedEnvelope):
        return _malformed_process_envelope_outcome(parsed.message)
    if isinstance(parsed, ProcessToolUnsupportedEnvelope):
        return _unsupported_process_envelope_outcome(parsed.status)
    raise TypeError("unsupported process tool envelope parse result")


def _malformed_process_envelope_outcome(message: str) -> ToolFailedOutcome:
    """构造 process-backed malformed envelope 失败 outcome。

    :param message: 失败诊断说明。
    :returns: 工具失败 outcome。
    :raises Exception: 不主动抛出异常。
    """

    return _tool_failed_outcome(
        error=_PROCESS_BACKED_TOOL_MALFORMED_ENVELOPE_ERROR,
        message=message,
        hint=None,
    )


def _unsupported_process_envelope_outcome(status: str) -> ToolFailedOutcome:
    """构造 process-backed unsupported envelope 失败 outcome。

    :param status: 子进程返回的 unsupported status。
    :returns: 工具失败 outcome。
    :raises Exception: 不主动抛出异常。
    """

    return _tool_failed_outcome(
        error=_PROCESS_BACKED_TOOL_UNSUPPORTED_ENVELOPE_ERROR,
        message=f"process envelope status is not supported: {status}",
        hint=None,
    )


def _duplicate_reason_code(kind: DuplicateDecisionKind) -> str:
    """返回 duplicate decision 对应的机器可读原因码。

    :param kind: duplicate 决策类别。
    :returns: 原因码。
    """

    if kind is DuplicateDecisionKind.REUSE:
        return _TOOL_RUNTIME_DUPLICATE_REUSE_REASON
    if kind is DuplicateDecisionKind.HINT:
        return _TOOL_RUNTIME_DUPLICATE_HINT_REASON
    if kind is DuplicateDecisionKind.REQUIRE_JUSTIFICATION:
        return _TOOL_RUNTIME_DUPLICATE_REQUIRE_JUSTIFICATION_REASON
    if kind is DuplicateDecisionKind.HARD_STOP:
        return _TOOL_RUNTIME_DUPLICATE_HARD_STOP_REASON
    if kind is DuplicateDecisionKind.DURABLE_MISSING:
        return "duplicate_prior_accept_missing"
    if kind is DuplicateDecisionKind.AWAITING_FANOUT:
        return _TOOL_RUNTIME_DUPLICATE_AWAITING_FANOUT_REASON
    return "duplicate_allowed"


def _tool_accept_duplicate_governance_from_decision(
    decision: DuplicateDecision,
    *,
    reuse_prior_event_refs: tuple[HostEventRef, ...],
) -> ToolAcceptDuplicateGovernance:
    """从 duplicate 决策构造 accept candidate 的治理子结构。

    :param decision: duplicate governance 决策。
    :param reuse_prior_event_refs: 当前 fact kind 允许携带的 prior event refs。
    :returns: duplicate governance 子结构。
    :raises ValueError: duplicate 决策缺少必填消息或作用域时抛出。
    """

    return ToolAcceptDuplicateGovernance(
        duplicate_key=decision.duplicate_key,
        duplicate_decision=decision.kind,
        duplicate_scope=decision.scope,
        duplicate_decision_message=decision.message,
        reuse_prior_event_refs=reuse_prior_event_refs,
    )


def _tool_fact_accept_candidate(
    *,
    scope: ToolRuntimeExecutionScope,
    effective_bundle: EffectiveToolBundle,
    call: ToolCallRequest,
    iteration_id: str,
    normalized_arguments_digest: str,
    outcome: ToolExecutionOutcome,
    truncation_fact: ToolTruncationFact | None,
    policy_decision: ToolPolicyDecision,
    duplicate_decision: DuplicateDecision,
    duplicate_governed: bool,
    tool_idempotency_key: str | None,
    diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...],
) -> ToolFactAcceptCandidate:
    """从工具 outcome 构造 Host accept candidate。

    :param scope: ToolRuntime 执行 scope。
    :param effective_bundle: effective 工具集合。
    :param call: 单次工具调用请求。
    :param iteration_id: 当前 Engine iteration id。
    :param normalized_arguments_digest: 参数 digest。
    :param outcome: 已治理并可进入 accept path 的 outcome。
    :param truncation_fact: 截断事实；未截断为 ``None``。
    :param policy_decision: 工具治理决策。
    :param duplicate_decision: duplicate governance 决策。
    :param duplicate_governed: 本次 governed outcome 是否由 duplicate
        governance 的非 allow 决策触发。
    :param tool_idempotency_key: 工具级幂等 key。
    :param diagnostic_refs: 诊断 refs。
    :returns: Host 工具事实候选。
    """

    tool_fact_kind = _tool_fact_kind(outcome, policy_decision)
    outcome_digest = _tool_outcome_digest(outcome)
    payload_digest = _tool_payload_digest(outcome)
    schema_digest = _tool_schema_digest_for_call(effective_bundle, call)
    identity_digest = _tool_identity_digest(
        effective_bundle=effective_bundle,
        tool_name=call.name,
        schema_digest=schema_digest,
    )
    semantic_input_digest = _tool_semantic_input_digest(
        scope=scope,
        call=call,
        tool_fact_kind=tool_fact_kind,
        normalized_arguments_digest=normalized_arguments_digest,
        outcome_digest=outcome_digest,
        payload_digest=payload_digest,
        policy_decision=policy_decision,
        duplicate_decision=duplicate_decision,
        truncation_fact=truncation_fact,
    )
    return ToolFactAcceptCandidate(
        identity=ToolAcceptIdentity(
            session_id=scope.session_id,
            run_id=scope.run_id,
            attempt_id=scope.attempt_id,
            execution_id=scope.execution_id,
        ),
        call=ToolAcceptCall(
            iteration_id=iteration_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            tool_schema_digest=schema_digest,
            tool_identity_digest=identity_digest,
            normalized_arguments_digest=normalized_arguments_digest,
            accepted_arguments=call.arguments,
        ),
        tool_fact_kind=tool_fact_kind,
        result=ToolAcceptResult(
            outcome_digest=outcome_digest,
            payload_digest=payload_digest,
            payload_ref=None,
            truncation=truncation_fact,
            raw_tool_outcome=_tool_outcome_json(outcome),
            tool_timing=_tool_timing_from_meta(_tool_result_meta(outcome)),
            failure_metadata=_failure_metadata_from_outcome(
                outcome=outcome,
                policy_decision=policy_decision,
                diagnostic_refs=diagnostic_refs,
            ),
        ),
        governance=ToolAcceptGovernance(
            policy_decision=policy_decision,
            tool_idempotency_key=tool_idempotency_key,
            duplicate=_tool_accept_duplicate_governance_from_decision(
                duplicate_decision,
                reuse_prior_event_refs=(
                    duplicate_decision.prior_event_refs
                    if (
                        tool_fact_kind is ToolFactKind.GOVERNED_ERROR
                        and duplicate_governed
                    )
                    else ()
                ),
            ),
        ),
        idempotency=ToolAcceptIdempotency(
            accept_idempotency_key=_tool_accept_idempotency_key(
                scope=scope,
                call=call,
                tool_fact_kind=tool_fact_kind,
                outcome_digest=outcome_digest,
                policy_decision=policy_decision,
            ),
            semantic_input_digest=semantic_input_digest,
        ),
        diagnostics=ToolAcceptDiagnostics(diagnostic_refs=diagnostic_refs),
    )


def _tool_fact_reuse_accept_candidate(
    *,
    scope: ToolRuntimeExecutionScope,
    effective_bundle: EffectiveToolBundle,
    call: ToolCallRequest,
    iteration_id: str,
    normalized_arguments_digest: str,
    prior_outcome: ToolExecutionOutcome,
    policy_decision: ToolPolicyDecision,
    duplicate_decision: DuplicateDecision,
    tool_idempotency_key: str | None,
    diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...],
) -> ToolFactAcceptCandidate:
    """从 duplicate reuse 决策构造 Host accept candidate。

    :param scope: ToolRuntime 执行 scope。
    :param effective_bundle: effective 工具集合。
    :param call: 单次工具调用请求。
    :param iteration_id: 当前 Engine iteration id。
    :param normalized_arguments_digest: 参数 digest。
    :param prior_outcome: 既有 accepted outcome，用于 digest 解释与返回 Engine。
    :param policy_decision: reuse policy decision。
    :param duplicate_decision: duplicate reuse 决策。
    :param tool_idempotency_key: 工具级幂等 key。
    :param diagnostic_refs: 诊断 refs。
    :returns: reuse 工具事实候选。
    :raises ValueError: duplicate decision 不是 reuse 或缺少 prior refs 时抛出。
    """

    if duplicate_decision.kind is not DuplicateDecisionKind.REUSE:
        raise ValueError("reuse candidate requires duplicate reuse decision")
    if not duplicate_decision.prior_event_refs:
        raise ValueError("reuse candidate requires prior event refs")
    schema_digest = _tool_schema_digest_for_call(effective_bundle, call)
    identity_digest = _tool_identity_digest(
        effective_bundle=effective_bundle,
        tool_name=call.name,
        schema_digest=schema_digest,
    )
    prior_outcome_digest = _tool_outcome_digest(prior_outcome)
    semantic_input_digest = _tool_semantic_input_digest(
        scope=scope,
        call=call,
        tool_fact_kind=ToolFactKind.REUSE,
        normalized_arguments_digest=normalized_arguments_digest,
        outcome_digest=prior_outcome_digest,
        payload_digest=None,
        policy_decision=policy_decision,
        duplicate_decision=duplicate_decision,
        truncation_fact=None,
    )
    return ToolFactAcceptCandidate(
        identity=ToolAcceptIdentity(
            session_id=scope.session_id,
            run_id=scope.run_id,
            attempt_id=scope.attempt_id,
            execution_id=scope.execution_id,
        ),
        call=ToolAcceptCall(
            iteration_id=iteration_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            tool_schema_digest=schema_digest,
            tool_identity_digest=identity_digest,
            normalized_arguments_digest=normalized_arguments_digest,
            accepted_arguments=call.arguments,
        ),
        tool_fact_kind=ToolFactKind.REUSE,
        result=None,
        governance=ToolAcceptGovernance(
            policy_decision=policy_decision,
            tool_idempotency_key=tool_idempotency_key,
            duplicate=_tool_accept_duplicate_governance_from_decision(
                duplicate_decision,
                reuse_prior_event_refs=duplicate_decision.prior_event_refs,
            ),
        ),
        idempotency=ToolAcceptIdempotency(
            accept_idempotency_key=_tool_accept_idempotency_key(
                scope=scope,
                call=call,
                tool_fact_kind=ToolFactKind.REUSE,
                outcome_digest=prior_outcome_digest,
                policy_decision=policy_decision,
            ),
            semantic_input_digest=semantic_input_digest,
        ),
        diagnostics=ToolAcceptDiagnostics(diagnostic_refs=diagnostic_refs),
    )


def _tool_awaiting_accept_candidate(
    *,
    scope: ToolRuntimeExecutionScope,
    call: ToolCallRequest,
    iteration_id: str,
    tool_schema_digest: str,
    tool_identity_digest: str,
    normalized_arguments_digest: str,
    awaiting_outcome: ToolAwaitingOutcome,
    snapshot_ref: WaitSnapshotRef | None,
    binding: WaitAdapterBinding,
    external_job_ref: ExternalJobRef | None,
    duplicate_decision: DuplicateDecision,
    policy_decision: ToolPolicyDecision,
) -> ToolAwaitingAcceptCandidate:
    """构造 awaiting accept candidate。

    :param scope: ToolRuntime 执行 scope。
    :param call: 单次工具调用请求。
    :param iteration_id: Engine iteration id。
    :param tool_schema_digest: 工具 schema digest。
    :param tool_identity_digest: 工具身份 digest。
    :param normalized_arguments_digest: 参数 digest。
    :param awaiting_outcome: 等待 outcome。
    :param snapshot_ref: 可选等待快照引用。
    :param binding: Host wait adapter binding。
    :param external_job_ref: 可选外部 job 引用。
    :param duplicate_decision: duplicate governance 决策。
    :param policy_decision: 工具治理决策。
    :returns: awaiting accept candidate。
    """

    base_digest = build_tool_awaiting_accept_identity_digest(
        session_id=scope.session_id,
        run_id=scope.run_id,
        attempt_id=scope.attempt_id,
        execution_id=scope.execution_id,
        iteration_id=iteration_id,
        tool_call_id=call.tool_call_id,
        tool_name=call.name,
        await_spec=awaiting_outcome.await_spec,
        adapter_key=binding.adapter_key.value,
        resume_policy=binding.resume_policy.value,
        external_job_id=(
            external_job_ref.external_job_id if external_job_ref is not None else None
        ),
        snapshot_id=snapshot_ref.snapshot_id if snapshot_ref is not None else None,
        normalized_arguments_digest=normalized_arguments_digest,
    )
    semantic_input_digest = sha256_digest_json(
        {
            "base_digest": base_digest,
            "tool_schema_digest": tool_schema_digest,
            "tool_identity_digest": tool_identity_digest,
            "policy_decision": _policy_decision_json(policy_decision),
            "duplicate_decision": _duplicate_decision_json(duplicate_decision),
        }
    )
    digest = semantic_input_digest.removeprefix("sha256:")
    return ToolAwaitingAcceptCandidate(
        session_id=scope.session_id,
        run_id=scope.run_id,
        attempt_id=scope.attempt_id,
        execution_id=scope.execution_id,
        iteration_id=iteration_id,
        tool_call_id=call.tool_call_id,
        tool_name=call.name,
        tool_schema_digest=tool_schema_digest,
        tool_identity_digest=tool_identity_digest,
        normalized_arguments_digest=normalized_arguments_digest,
        accepted_arguments=call.arguments,
        await_spec=awaiting_outcome.await_spec,
        snapshot_ref=snapshot_ref,
        binding=binding,
        external_job_ref=external_job_ref,
        wait_id=f"wait-{digest}",
        accept_idempotency_key=f"tool-await-{digest}",
        semantic_input_digest=semantic_input_digest,
    )


def _wait_snapshot_ref(outcome: ToolAwaitingOutcome) -> WaitSnapshotRef | None:
    """从 awaiting outcome 构造 wait snapshot ref。

    :param outcome: 等待 outcome。
    :returns: wait snapshot ref；无快照时为 ``None``。
    """

    if outcome.snapshot is None:
        return None
    return WaitSnapshotRef(
        snapshot_id=outcome.snapshot.snapshot_id,
        captured_at=outcome.snapshot.captured_at,
        snapshot_digest=_wait_snapshot_digest(outcome.snapshot),
    )


def _wait_snapshot_digest(snapshot: ToolAwaitSnapshot) -> str:
    """计算 Engine awaiting snapshot 的 Host durable 引用 digest。

    :param snapshot: Engine 透传的等待时点快照引用。
    :returns: Host durable 标准 sha256 digest。
    """

    return sha256_digest_json(
        {
            "captured_at": format_utc_timestamp(snapshot.captured_at),
            "snapshot_id": snapshot.snapshot_id,
        }
    )


def _tool_fact_kind(
    outcome: ToolExecutionOutcome, policy_decision: ToolPolicyDecision
) -> ToolFactKind:
    """把工具 outcome 映射为 canonical fact kind。

    :param outcome: 工具 outcome。
    :param policy_decision: 工具治理决策。
    :returns: Host canonical fact kind。
    :raises TypeError: 收到 P6-S3 不支持的 awaiting outcome 时抛出。
    """

    if policy_decision.kind is not ToolPolicyDecisionKind.ALLOW:
        return ToolFactKind.GOVERNED_ERROR
    if isinstance(outcome, ToolCompletedOutcome):
        return ToolFactKind.COMPLETED
    if isinstance(outcome, ToolFailedOutcome):
        return ToolFactKind.FAILED
    if isinstance(outcome, ToolCancelledOutcome):
        return ToolFactKind.CANCELLED
    if isinstance(outcome, ToolAwaitingOutcome):
        raise TypeError("ToolAwaitingOutcome must be normalized before accept")
    raise TypeError("unsupported tool outcome")


def _tool_outcome_digest(outcome: ToolExecutionOutcome) -> str:
    """计算工具 outcome digest。

    :param outcome: 工具 outcome。
    :returns: Host canonical sha256 digest。
    """

    if isinstance(
        outcome, ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome
    ):
        return accepted_tool_outcome_digest(outcome)
    return sha256_digest_json(_tool_outcome_json(outcome))


def _tool_outcome_inline_size_bytes(outcome: ToolExecutionOutcome) -> int:
    """估算工具 outcome 进入 LLM inline tool message 的 UTF-8 字节数。

    :param outcome: 工具 outcome。
    :returns: canonical JSON 投影的 UTF-8 字节数。
    :raises TypeError: 收到不支持的工具 outcome 时抛出。
    """

    if isinstance(
        outcome, ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome
    ):
        return accepted_tool_outcome_inline_size_bytes(outcome)
    return len(canonical_json_dumps(_tool_outcome_json(outcome)).encode("utf-8"))


def _tool_payload_digest(outcome: ToolExecutionOutcome) -> str | None:
    """计算 completed outcome 的 payload digest。

    :param outcome: 工具 outcome。
    :returns: completed payload digest；其它 outcome 为 ``None``。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        return sha256_digest_json({"value": outcome.result.value})
    return None


def _tool_schema_digest_for_call(
    effective_bundle: EffectiveToolBundle, call: ToolCallRequest
) -> str:
    """计算单工具 schema digest。

    :param effective_bundle: effective 工具集合。
    :param call: 单次工具调用请求。
    :returns: 单工具 schema digest；未知工具使用诊断 digest。
    """

    definition = effective_bundle.definitions_by_name.get(call.name)
    if definition is None:
        return sha256_digest_json({"unknown_tool_name": call.name})
    return sha256_digest_json(_tool_schema_json(definition.schema))


def _tool_identity_digest(
    *,
    effective_bundle: EffectiveToolBundle,
    tool_name: str,
    schema_digest: str,
) -> str:
    """计算工具身份 digest。

    :param effective_bundle: effective 工具集合。
    :param tool_name: 工具名。
    :param schema_digest: 单工具 schema digest。
    :returns: 工具身份 digest。
    """

    return sha256_digest_json(
        {
            "tool_name": tool_name,
            "schema_digest": schema_digest,
            "business_bundle_digest": effective_bundle.business_bundle_digest,
        }
    )


def _tool_semantic_input_digest(
    *,
    scope: ToolRuntimeExecutionScope,
    call: ToolCallRequest,
    tool_fact_kind: ToolFactKind,
    normalized_arguments_digest: str,
    outcome_digest: str,
    payload_digest: str | None,
    policy_decision: ToolPolicyDecision,
    duplicate_decision: DuplicateDecision,
    truncation_fact: ToolTruncationFact | None,
) -> str:
    """计算 accept candidate semantic input digest。

    :param scope: ToolRuntime 执行 scope。
    :param call: 单次工具调用请求。
    :param tool_fact_kind: canonical fact kind。
    :param normalized_arguments_digest: 参数 digest。
    :param outcome_digest: outcome digest。
    :param payload_digest: payload digest。
    :param policy_decision: policy decision。
    :param duplicate_decision: duplicate decision。
    :param truncation_fact: 截断事实。
    :returns: Host canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "attempt_id": scope.attempt_id,
            "execution_id": scope.execution_id,
            "tool_call_id": call.tool_call_id,
            "tool_name": call.name,
            "tool_fact_kind": tool_fact_kind.value,
            "normalized_arguments_digest": normalized_arguments_digest,
            "outcome_digest": outcome_digest,
            "payload_digest": payload_digest,
            "policy_decision": _policy_decision_json(policy_decision),
            "duplicate_decision": _duplicate_decision_json(duplicate_decision),
            "truncation": _truncation_json(truncation_fact),
        }
    )


def _tool_accept_idempotency_key(
    *,
    scope: ToolRuntimeExecutionScope,
    call: ToolCallRequest,
    tool_fact_kind: ToolFactKind,
    outcome_digest: str,
    policy_decision: ToolPolicyDecision,
) -> str:
    """派生 Host accept 幂等 key。

    :param scope: ToolRuntime 执行 scope。
    :param call: 单次工具调用请求。
    :param tool_fact_kind: canonical fact kind。
    :param outcome_digest: outcome digest。
    :param policy_decision: policy decision。
    :returns: 稳定 accept 幂等 key。
    """

    digest = sha256_digest_json(
        {
            "attempt_id": scope.attempt_id,
            "execution_id": scope.execution_id,
            "tool_call_id": call.tool_call_id,
            "tool_fact_kind": tool_fact_kind.value,
            "outcome_digest": outcome_digest,
            "policy_decision": _policy_decision_json(policy_decision),
        }
    ).removeprefix("sha256:")
    return f"tool-accept-{digest}"


def _tool_result_meta(outcome: ToolExecutionOutcome) -> ToolResultMeta | None:
    """从普通工具 outcome 中提取结果 meta。

    :param outcome: completed / failed / cancelled 工具 outcome。
    :returns: outcome 携带的 ``ToolResultMeta``；缺失时为 ``None``。
    :raises TypeError: 收到 awaiting 或未知 outcome 时抛出。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        return outcome.result.meta
    if isinstance(outcome, ToolFailedOutcome):
        return outcome.result.meta
    if isinstance(outcome, ToolCancelledOutcome):
        return outcome.meta
    if isinstance(outcome, ToolAwaitingOutcome):
        raise TypeError("ToolAwaitingOutcome does not carry accepted result timing")
    raise TypeError("unsupported tool outcome")


def _tool_timing_from_meta(meta: ToolResultMeta | None) -> Mapping[str, JsonValue]:
    """从工具结果 meta 构造稳定耗时 signal。

    :param meta: 工具结果 meta。
    :returns: ``tool_timing`` JSON object。
    :raises ValueError: meta 时间产生负耗时时抛出。
    """

    if meta is None:
        return {
            "schema_version": _TOOL_TIMING_SCHEMA_VERSION,
            "status": _TOOL_TIMING_STATUS_MISSING_META,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "duration_source": None,
        }
    duration_ms = int((meta.finished_at - meta.started_at) // _ONE_MILLISECOND)
    if duration_ms < 0:
        raise ValueError("tool_timing.duration_ms must be non-negative")
    return {
        "schema_version": _TOOL_TIMING_SCHEMA_VERSION,
        "status": _TOOL_TIMING_STATUS_AVAILABLE,
        "started_at": meta.started_at.isoformat(),
        "finished_at": meta.finished_at.isoformat(),
        "duration_ms": duration_ms,
        "duration_source": _TOOL_TIMING_DURATION_SOURCE_META,
    }


def _failure_metadata_from_outcome(
    *,
    outcome: ToolExecutionOutcome,
    policy_decision: ToolPolicyDecision,
    diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...],
) -> Mapping[str, JsonValue] | None:
    """从 typed outcome 与治理决策构造失败元数据 signal。

    :param outcome: 工具执行 outcome。
    :param policy_decision: 工具治理决策。
    :param diagnostic_refs: 本次工具事实携带的诊断引用。
    :returns: failure metadata JSON object；成功结果为 ``None``。
    :raises TypeError: 收到 awaiting 或未知 outcome 时抛出。
    """

    diagnostic_ref_ids: list[JsonValue] = [ref.ref_id for ref in diagnostic_refs]
    if policy_decision.kind is not ToolPolicyDecisionKind.ALLOW:
        return {
            "schema_version": _FAILURE_METADATA_SCHEMA_VERSION,
            "signal_source": _FAILURE_SIGNAL_SOURCE_TOOL_RESULT_ACCEPTED,
            "failure_kind": _FAILURE_KIND_POLICY_BLOCKED,
            "policy_decision_kind": policy_decision.kind.value,
            "policy_block_reason": policy_decision.reason_code,
            "diagnostic_refs": diagnostic_ref_ids,
        }
    if isinstance(outcome, ToolCompletedOutcome):
        return None
    if isinstance(outcome, ToolFailedOutcome):
        bounded_hint = bound_trace_signal_text(outcome.result.hint)
        return {
            "schema_version": _FAILURE_METADATA_SCHEMA_VERSION,
            "signal_source": _FAILURE_SIGNAL_SOURCE_TOOL_RESULT_ACCEPTED,
            "failure_kind": _FAILURE_KIND_TOOL_FAILED,
            "error_code": outcome.result.error,
            "repair_hint": bounded_hint.value,
            "repair_hint_truncated": bounded_hint.truncated,
            "repair_hint_sha256": bounded_hint.sha256_digest,
            "diagnostic_refs": diagnostic_ref_ids,
        }
    if isinstance(outcome, ToolCancelledOutcome):
        bounded_message = bound_trace_signal_text(outcome.message)
        bounded_hint = bound_trace_signal_text(outcome.hint)
        return {
            "schema_version": _FAILURE_METADATA_SCHEMA_VERSION,
            "signal_source": _FAILURE_SIGNAL_SOURCE_TOOL_RESULT_ACCEPTED,
            "failure_kind": _FAILURE_KIND_TOOL_CANCELLED,
            "cancel_reason": outcome.reason,
            "cancel_message": bounded_message.value,
            "cancel_message_truncated": bounded_message.truncated,
            "cancel_message_sha256": bounded_message.sha256_digest,
            "cancel_hint": bounded_hint.value,
            "cancel_hint_truncated": bounded_hint.truncated,
            "cancel_hint_sha256": bounded_hint.sha256_digest,
            "diagnostic_refs": diagnostic_ref_ids,
        }
    if isinstance(outcome, ToolAwaitingOutcome):
        raise TypeError("ToolAwaitingOutcome does not carry accepted failure metadata")
    raise TypeError("unsupported tool outcome")


def _tool_outcome_json(outcome: ToolExecutionOutcome) -> JsonValue:
    """把工具 outcome 投影为 JSON digest 输入。

    :param outcome: 工具 outcome。
    :returns: JSON digest 输入。
    :raises TypeError: 收到 awaiting outcome 时抛出。
    """

    if isinstance(
        outcome, ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome
    ):
        return accepted_tool_outcome_json(outcome)
    if isinstance(outcome, ToolAwaitingOutcome):
        return {
            "kind": "awaiting",
            "await_spec": {
                "await_kind": outcome.await_spec.await_kind.value,
                "deadline": (
                    outcome.await_spec.deadline.isoformat()
                    if outcome.await_spec.deadline is not None
                    else None
                ),
                "resume_token": outcome.await_spec.resume_token,
            },
            "snapshot": (
                {
                    "snapshot_id": outcome.snapshot.snapshot_id,
                    "captured_at": outcome.snapshot.captured_at.isoformat(),
                }
                if outcome.snapshot is not None
                else None
            ),
        }
    raise TypeError("unsupported tool outcome")


def _duplicate_decision_json(decision: DuplicateDecision) -> JsonValue:
    """把 duplicate decision 投影为 JSON。

    :param decision: duplicate decision。
    :returns: JSON mapping。
    """

    return {
        "kind": decision.kind.value,
        "duplicate_key": decision.duplicate_key,
        "duplicate_scope": _duplicate_scope_json(decision.scope),
        "reason_code": decision.reason_code,
        "message": decision.message,
        "diagnostic_message": decision.diagnostic_message,
        "prior_event_refs": [
            _event_ref_json(ref) for ref in decision.prior_event_refs
        ],
    }


def _tool_failed_outcome(
    *, error: str, message: str, hint: str | None
) -> ToolFailedOutcome:
    """构造工具失败 outcome。

    :param error: 错误码。
    :param message: 人类可读错误。
    :param hint: 可选恢复提示。
    :returns: ``ToolFailedOutcome``。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=error,
            message=message,
            hint=hint,
            meta=None,
        )
    )


def _batch_timeout_deadline(timeout_seconds: float | None) -> float | None:
    """把批级 timeout 秒数转换为单调时钟 deadline。

    :param timeout_seconds: 批级 timeout 秒数；无 timeout 时为 ``None``。
    :returns: 单调时钟 deadline；无 timeout 时为 ``None``。
    """

    if timeout_seconds is None:
        return None
    return time.monotonic() + timeout_seconds


def _remaining_batch_timeout_seconds(deadline: float | None) -> float | None:
    """读取批级 timeout 剩余秒数。

    :param deadline: 单调时钟 deadline；无 timeout 时为 ``None``。
    :returns: 剩余秒数；无 timeout 时为 ``None``。
    """

    if deadline is None:
        return None
    return deadline - time.monotonic()


def _runtime_cancelled_policy_decision(reason: str | None) -> ToolPolicyDecision:
    """构造 ToolRuntime cancellation 治理决策。

    :param reason: cancellation token 提供的取消原因。
    :returns: governed error 决策。
    """

    message = "工具调用在完成前已停止"
    if reason is not None:
        message = f"{message}: {reason}"
    return ToolPolicyDecision(
        kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
        reason_code=_TOOL_RUNTIME_CANCELLED_REASON,
        message=message,
    )


def _runtime_timeout_policy_decision(elapsed_seconds: float) -> ToolPolicyDecision:
    """构造 ToolRuntime timeout 治理决策。

    :param elapsed_seconds: runtime helper 观察到的等待耗时秒数。
    :returns: governed error 决策。
    """

    return ToolPolicyDecision(
        kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
        reason_code=_TOOL_RUNTIME_TIMEOUT_REASON,
        message=f"tool execution timed out after {elapsed_seconds:.6f} seconds",
    )


def _tool_interrupt_result_from_process(
    result: ProcessInterruptResult,
    *,
    success_message: str,
    pending_message: str,
) -> ToolInterruptStepResult:
    """把 runtime process interrupt 结果映射为 ToolRuntime 结果。

    :param result: runtime process interrupt 结果。
    :param success_message: 进程已退出时的诊断说明。
    :param pending_message: 进程仍未退出时的诊断说明。
    :returns: ToolRuntime interrupt 步骤结果。
    """

    if result.exited:
        return ToolInterruptStepResult(
            supported=result.supported,
            completed=True,
            message=success_message,
        )
    return ToolInterruptStepResult(
        supported=result.supported,
        completed=False,
        message=pending_message,
    )


def _truncation_failure(message: str) -> ToolFailedOutcome:
    """构造截断 / 补读失败工具 outcome。

    :param message: 人类可读错误。
    :returns: 普通 ``ToolFailedOutcome``。
    """

    return _tool_failed_outcome(
        error=_TRUNCATION_ERROR_CODE,
        message=message,
        hint=None,
    )


def _governed_failure_outcome(
    policy_decision: ToolPolicyDecision,
) -> ToolFailedOutcome:
    """按 policy decision 构造 governed failure outcome。

    :param policy_decision: 工具治理决策。
    :returns: governed ``ToolFailedOutcome``。
    """

    return _tool_failed_outcome(
        error=_TOOL_RUNTIME_POLICY_BLOCKED_ERROR,
        message=policy_decision.message or _TOOL_RUNTIME_GOVERNED_ERROR,
        hint=None,
    )


def _accept_failure_outcome(
    result: ToolFactRejectedAck | ToolFactAcceptTimedOut,
) -> ToolFailedOutcome:
    """把 accept failure 归一为不含原始业务结果的 governed error。

    :param result: rejected ack 或 timeout。
    :returns: governed ``ToolFailedOutcome``。
    """

    if isinstance(result, ToolFactRejectedAck):
        return _tool_failed_outcome(
            error=_TOOL_RUNTIME_ACCEPT_REJECTED_ERROR,
            message=result.message,
            hint=None,
        )
    return _tool_failed_outcome(
        error=_TOOL_RUNTIME_ACCEPT_TIMEOUT_ERROR,
        message=_accept_timeout_message(
            "tool fact accept ack timed out",
            result.last_error_code,
        ),
        hint=None,
    )


def _awaiting_accept_failure_outcome(
    result: ToolAwaitingRejectedAck | ToolAwaitingAcceptTimedOut,
) -> ToolFailedOutcome:
    """把 awaiting accept failure 归一为不含原始业务结果的 governed error。

    :param result: awaiting rejected ack 或 timeout。
    :returns: governed ``ToolFailedOutcome``。
    """

    if isinstance(result, ToolAwaitingRejectedAck):
        return _tool_failed_outcome(
            error=_TOOL_RUNTIME_AWAITING_ACCEPT_REJECTED_ERROR,
            message=result.message,
            hint=None,
        )
    return _tool_failed_outcome(
        error=_TOOL_RUNTIME_AWAITING_ACCEPT_TIMEOUT_ERROR,
        message=_accept_timeout_message(
            "tool awaiting accept ack timed out",
            result.last_error_code,
        ),
        hint=None,
    )


def _accept_timeout_message(message: str, last_error_code: str | None) -> str:
    """构造保留最后 accept 错误码的失败说明。

    :param message: 基础失败说明。
    :param last_error_code: accept owner 记录的最后错误码；无则为 ``None``。
    :returns: 保留必要错误码后的说明。
    """

    if last_error_code is None:
        return message
    return f"{message} (last_error_code={last_error_code})"


__all__ = [
    "AsyncDirectToolExecutionCapsule",
    "DeclaredToolExecutionCapsuleFactory",
    "DefaultToolDispatcher",
    "DefaultToolExecutionCapsuleFactory",
    "DefaultToolRuntimeFactory",
    "DefaultHostToolFactAcceptPort",
    "DefaultToolRuntimePolicyPort",
    "DeterministicToolTraceDiagnosticEmitter",
    "EffectiveToolBundle",
    "EffectiveToolBundleBuildRequest",
    "EffectiveToolBundleBuilder",
    "FetchMoreRequest",
    "FetchMoreResult",
    "FetchMoreToolCallable",
    "FrameworkToolInjector",
    "HostEventRef",
    "HostPayloadRef",
    "HostToolFactAcceptPort",
    "HostToolAwaitingAcceptPort",
    "InMemoryToolTraceDiagnosticEmitter",
    "NoopToolTraceDiagnosticEmitter",
    "NoopTruncationPort",
    "ProcessBackedToolExecutionCapsule",
    "ThreadBackedToolCallable",
    "ThreadBackedToolExecutionCapsule",
    "ToolExecutionCapsule",
    "ToolExecutionCapsuleFactory",
    "ToolExecutionMode",
    "ToolInterruptStepResult",
    "ToolSideEffectKind",
    "ToolAcceptRejectReason",
    "ToolAcceptRetryPolicy",
    "ToolDispatcher",
    "ToolFactAcceptCandidate",
    "ToolFactAcceptResult",
    "ToolFactAcceptTimedOut",
    "ToolFactAcceptedAck",
    "ToolFactKind",
    "ToolFactRejectedAck",
    "ToolAwaitingAcceptCandidate",
    "ToolAwaitingAcceptRejectReason",
    "ToolAwaitingAcceptResult",
    "ToolAwaitingAcceptTimedOut",
    "ToolAwaitingAcceptedAck",
    "ToolAwaitingEventRef",
    "ToolAwaitingRejectedAck",
    "ToolPolicyDecision",
    "ToolPolicyDecisionKind",
    "ToolRuntimeExecutionScope",
    "ToolRuntimeExecutor",
    "ToolRuntimePolicyView",
    "ToolRuntimeToolPolicy",
    "ToolRuntimeBuildRequest",
    "ToolRuntimeFactory",
    "ToolRuntimeHandle",
    "ToolRuntimePolicyPort",
    "ToolRuntimeUnsupportedExecutor",
    "ToolTraceDiagnosticEmitter",
    "ToolTraceDiagnosticRecord",
    "ToolTraceDiagnosticRef",
    "ToolTruncationCursor",
    "ToolTruncationFact",
    "TruncationAppliedOutcome",
    "TruncatedRemainderRef",
    "TruncationManager",
    "TruncationPort",
    "BinaryBytesRemainderRef",
    "ListItemsRemainderRef",
    "TextCharsRemainderRef",
    "TextLinesRemainderRef",
]
