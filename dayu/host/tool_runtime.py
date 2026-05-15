"""Host ToolRuntime 的 attempt-local typed ports。

本模块只落地 Phase 6 S1 需要的 ToolRuntime 装配边界：把外部业务
``ToolBundle`` 与可选 framework tool 注入合成为同一个
``EffectiveToolBundle``，并由 ``ToolRuntimeHandle`` 同时暴露 Engine
可见 schema 与批式 ``ToolExecutor``。P6-S2 在同一模块内补齐 Host accept
barrier 的 typed contract 与 durable accept port；真实工具调用、截断、
fetch_more callable、重复治理算法仍由后续 slice 实现。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure
from dayu.contracts.tool_schema import (
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
)
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.durable.codec import is_sha256_digest, sha256_digest_json
from dayu.host.durable.errors import (
    HostDurableError,
    HostIdempotencyConflictError,
    HostPayloadReferenceError,
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
    IdempotencyScope,
    IdempotencyStore,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.tooling import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    ToolBundleSourceRef,
)

_UNSUPPORTED_EXECUTOR_ERROR = "tool_runtime_not_connected"
_UNSUPPORTED_EXECUTOR_MESSAGE = (
    "ToolRuntime executor is not connected in Phase 6 S1"
)
_TOOL_FACT_ACCEPT_SCOPE_KIND = "tool_fact_accept"
_TOOL_FACT_ACCEPT_RESULT_KIND = "tool_fact_accept_ack"
_EVENT_ID_TOOL_CALL_REQUESTED_PREFIX = "event-tool-call-requested-"
_EVENT_ID_TOOL_CALL_GOVERNED_PREFIX = "event-tool-call-governed-"
_EVENT_ID_TOOL_RESULT_ACCEPTED_PREFIX = "event-tool-result-accepted-"
_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_CALL_GOVERNED = "TOOL_CALL_GOVERNED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_TOOL_ACCEPT_EVENT_ACTOR = "host.tool_runtime"
_TOOL_ACCEPT_EVENT_SOURCE = "host.tool_runtime.accept"
_MIN_ACCEPT_RETRY_ATTEMPTS = 1
_MIN_ACCEPT_BACKOFF_SECONDS = 0.0


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


class DuplicateDecisionKind(StrEnum):
    """同 Run 语义级重复工具调用决策类别。"""

    ALLOW = "allow"
    REUSE = "reuse"
    HINT = "hint"
    REQUIRE_JUSTIFICATION = "require_justification"
    HARD_STOP = "hard_stop"


class ToolFactKind(StrEnum):
    """Host canonical 工具事实类别。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
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
class HostPayloadRef:
    """Host payload descriptor 引用。

    :param payload_ref: payload descriptor 标识。
    :param payload_digest: payload 内容 digest。
    """

    payload_ref: str
    payload_digest: str

    def __post_init__(self) -> None:
        """校验 payload 引用字段。

        :returns: ``None``。
        :raises ValueError: 引用为空或 digest 非法时抛出。
        """

        _require_non_empty_text(self.payload_ref, field_name="payload_ref")
        _require_sha256_digest(self.payload_digest, field_name="payload_digest")


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
class ToolFactAcceptCandidate:
    """Host accept barrier 的工具事实候选。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param iteration_id: Engine iteration id。
    :param tool_call_id: tool call id。
    :param tool_name: 工具名。
    :param tool_schema_digest: 工具 schema digest。
    :param tool_identity_digest: 工具身份 digest。
    :param normalized_arguments_digest: 规范化参数 digest。
    :param tool_fact_kind: canonical 工具事实类别。
    :param outcome_digest: outcome digest；无新 outcome 的 reuse 可为 ``None``。
    :param payload_digest: result payload digest；无 result payload 时为 ``None``。
    :param payload_ref: result payload descriptor 引用。
    :param truncation: 截断事实；无截断时为 ``None``。
    :param duplicate_key: run-local duplicate key。
    :param duplicate_decision: duplicate governance 决策。
    :param reuse_prior_event_refs: reuse 指向的既有 accepted event refs。
    :param policy_decision: 工具治理决策。
    :param tool_idempotency_key: 工具自身幂等 key；无则为 ``None``。
    :param diagnostic_refs: 工具诊断引用。
    :param accept_idempotency_key: Host accept 幂等 key。
    :param semantic_input_digest: Host accept semantic input digest。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    iteration_id: str
    tool_call_id: str
    tool_name: str
    tool_schema_digest: str
    tool_identity_digest: str
    normalized_arguments_digest: str
    tool_fact_kind: ToolFactKind
    outcome_digest: str | None
    payload_digest: str | None
    payload_ref: HostPayloadRef | None
    truncation: ToolTruncationFact | None
    duplicate_key: str | None
    duplicate_decision: DuplicateDecisionKind | None
    reuse_prior_event_refs: tuple[HostEventRef, ...]
    policy_decision: ToolPolicyDecision
    tool_idempotency_key: str | None
    diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]
    accept_idempotency_key: str
    semantic_input_digest: str

    def __post_init__(self) -> None:
        """按工具事实类别校验候选字段。

        :returns: ``None``。
        :raises ValueError: 候选缺少必填字段或字段组合违反 fact kind 语义时抛出。
        """

        _validate_common_candidate_fields(self)
        _validate_duplicate_fields(self)
        if self.tool_fact_kind is ToolFactKind.COMPLETED:
            _require_sha256_digest(self.outcome_digest, field_name="outcome_digest")
            _require_sha256_digest(self.payload_digest, field_name="payload_digest")
        elif self.tool_fact_kind in (
            ToolFactKind.FAILED,
            ToolFactKind.CANCELLED,
            ToolFactKind.GOVERNED_ERROR,
        ):
            _require_sha256_digest(self.outcome_digest, field_name="outcome_digest")
            if self.reuse_prior_event_refs:
                raise ValueError(
                    f"{self.tool_fact_kind.value} must not carry prior reuse refs"
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


ToolFactAcceptResult = (
    ToolFactAcceptedAck | ToolFactRejectedAck | ToolFactAcceptTimedOut
)


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    """重复工具调用治理决策。

    :param kind: 重复治理类别。
    :param duplicate_key: 当前调用的重复键；未产生时为 ``None``。
    :param prior_event_refs: 可复用的既有事件引用；无复用时为空元组。
    """

    kind: DuplicateDecisionKind
    duplicate_key: str | None
    prior_event_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TruncationAppliedOutcome:
    """截断端口输出。

    :param outcome: 可能已被截断改写的工具 outcome。
    :param cursor_hint: 普通工具结果中可提示 ``fetch_more`` 的 cursor；无为 ``None``。
    """

    outcome: ToolExecutionOutcome
    cursor_hint: str | None


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
        outcome: ToolExecutionOutcome,
        truncate_spec: ToolTruncateSpec | None,
    ) -> TruncationAppliedOutcome:
        """应用工具结果截断策略。

        :param tool_name: 工具名。
        :param outcome: 原始工具 outcome。
        :param truncate_spec: effective bundle 中同名工具的截断声明。
        :returns: 截断后的 outcome 与 cursor hint。
        """
        ...


class DuplicateGovernancePort(Protocol):
    """重复工具调用治理端口协议。"""

    def decide_duplicate(
        self, tool_name: str, normalized_arguments_digest: str
    ) -> DuplicateDecision:
        """判断当前工具调用是否与同 Run 既有调用重复。

        :param tool_name: 工具名。
        :param normalized_arguments_digest: canonical 参数摘要。
        :returns: 重复治理决策。
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


class DefaultHostToolFactAcceptPort:
    """基于 Host durable store 的工具事实 accept barrier 实现。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore | None = None,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        """初始化默认 accept port。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog primitive；无则创建默认实现。
        :param idempotency_store: Idempotency primitive；无则创建默认实现。
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

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """接受工具事实候选并写入 canonical EventLog facts。

        :param candidate: 工具事实候选。
        :returns: accepted ack、rejected ack 或 timeout 结果。
        """

        try:
            return self._transaction_runner.run_write(
                lambda transaction: self._accept_in_transaction(
                    transaction, candidate
                )
            )
        except HostIdempotencyConflictError:
            return _rejected_ack(
                candidate,
                ToolAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                "tool fact accept idempotency conflict",
                retryable=False,
            )
        except HostPayloadReferenceError:
            return _rejected_ack(
                candidate,
                ToolAcceptRejectReason.PAYLOAD_REFERENCE_INVALID,
                "tool fact payload reference is invalid",
                retryable=False,
            )

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
            if existing.semantic_input_digest != candidate.semantic_input_digest:
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

        event_plan = _tool_accept_event_plan(candidate)
        requested = self._event_log_store.append_event(
            transaction,
            _tool_call_requested_event_request(candidate, event_plan.requested_id),
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
            candidate.semantic_input_digest,
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


@dataclass(frozen=True, slots=True)
class EffectiveToolBundleBuildRequest:
    """EffectiveToolBundleBuilder 的输入。

    :param business_tool_bundle: 外部装配好的业务工具集合。
    :param source_refs: 业务工具来源引用。
    :param framework_tool_policy: framework tool policy view。
    :param policy_snapshot_digest: policy snapshot 摘要；无时为 ``None``。
    """

    business_tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    framework_tool_policy: FrameworkToolPolicyView
    policy_snapshot_digest: str | None


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
        definitions = list(request.business_tool_bundle.definitions)
        injected = self._inject_framework_definitions(request.framework_tool_policy)
        definitions.extend(injected)
        definitions_by_name = _definitions_by_name(definitions)
        tool_schemas = tuple(
            definition.to_tool_schema() for definition in definitions
        )
        truncate_specs = {
            definition.name: definition.truncate
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
        )

    def _inject_framework_definitions(
        self, policy: FrameworkToolPolicyView
    ) -> tuple[ToolDefinition, ...]:
        """按 policy 通过 hook 注入 framework tool。

        :param policy: framework tool policy view。
        :returns: 实际注入的工具声明元组。
        :raises ValueError: hook 返回的工具名与请求名称不一致时抛出。
        """

        if self._framework_injector is None:
            return ()
        definitions: list[ToolDefinition] = []
        for tool_name in sorted(
            policy.enabled_framework_tools, key=lambda item: item.value
        ):
            definition = self._framework_injector.build_framework_tool(tool_name)
            if definition.name != tool_name.value:
                raise ValueError(
                    "framework injector returned mismatched tool name:"
                    f" {definition.name}"
                )
            definitions.append(definition)
        return tuple(definitions)


@dataclass(frozen=True, slots=True)
class ToolRuntimeBuildRequest:
    """ToolRuntime factory 构造输入。

    :param effective_bundle_request: effective bundle 构造输入。
    """

    effective_bundle_request: EffectiveToolBundleBuildRequest


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

    本 factory 只创建 P6-S1 的 unsupported executor，不执行真实工具。
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
        return ToolRuntimeHandle(
            effective_bundle=effective_bundle,
            tool_schemas=effective_bundle.tool_schemas,
            tool_executor=ToolRuntimeUnsupportedExecutor(effective_bundle),
        )


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


def _accept_idempotency_scope(candidate: ToolFactAcceptCandidate) -> IdempotencyScope:
    """构造工具事实 accept 幂等作用域。

    :param candidate: 工具事实候选。
    :returns: 幂等作用域。
    """

    return IdempotencyScope(
        scope_kind=_TOOL_FACT_ACCEPT_SCOPE_KIND,
        scope_id=f"{candidate.attempt_id}:{candidate.tool_call_id}",
        idempotency_key=candidate.accept_idempotency_key,
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
        run=read_run_by_id(transaction, candidate.run_id),
        attempt=read_attempt_by_id(transaction, candidate.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, candidate.attempt_id
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
        context.run.session_id != candidate.session_id
        or context.run.run_id != candidate.run_id
        or context.run.current_attempt_id != candidate.attempt_id
        or context.attempt.run_id != candidate.run_id
    ):
        return ToolAcceptRejectReason.INVALID_ATTEMPT
    if (
        context.attempt.execution_id != candidate.execution_id
        or context.dispatch_record.execution_id != candidate.execution_id
        or context.dispatch_record.run_id != candidate.run_id
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


def _tool_accept_event_plan(candidate: ToolFactAcceptCandidate) -> _ToolAcceptEventPlan:
    """为工具 accept candidate 派生稳定事件 id。

    :param candidate: 工具事实候选。
    :returns: 事件 id 规划。
    """

    digest_input: dict[str, JsonValue] = {
        "session_id": candidate.session_id,
        "run_id": candidate.run_id,
        "attempt_id": candidate.attempt_id,
        "execution_id": candidate.execution_id,
        "iteration_id": candidate.iteration_id,
        "tool_call_id": candidate.tool_call_id,
        "tool_fact_kind": candidate.tool_fact_kind.value,
        "accept_idempotency_key": candidate.accept_idempotency_key,
        "semantic_input_digest": candidate.semantic_input_digest,
    }
    digest = sha256_digest_json(digest_input).removeprefix("sha256:")
    tool_fact_id = f"tool-fact-{digest}"
    return _ToolAcceptEventPlan(
        tool_fact_id=tool_fact_id,
        requested_id=f"{_EVENT_ID_TOOL_CALL_REQUESTED_PREFIX}{digest}",
        governed_id=f"{_EVENT_ID_TOOL_CALL_GOVERNED_PREFIX}{digest}",
        result_id=f"{_EVENT_ID_TOOL_RESULT_ACCEPTED_PREFIX}{digest}",
    )


def _tool_call_requested_event_request(
    candidate: ToolFactAcceptCandidate, event_id: str
) -> EventLogAppendRequest:
    """构造 ``TOOL_CALL_REQUESTED`` append request。

    :param candidate: 工具事实候选。
    :param event_id: 稳定事件 id。
    :returns: EventLog append request。
    """

    return _tool_event_request(
        candidate,
        event_id=event_id,
        event_type=_EVENT_TYPE_TOOL_CALL_REQUESTED,
        policy_decision=None,
        reason=None,
        payload={
            "session_id": candidate.session_id,
            "run_id": candidate.run_id,
            "attempt_id": candidate.attempt_id,
            "execution_id": candidate.execution_id,
            "iteration_id": candidate.iteration_id,
            "tool_call_id": candidate.tool_call_id,
            "tool_name": candidate.tool_name,
            "tool_schema_digest": candidate.tool_schema_digest,
            "tool_identity_digest": candidate.tool_identity_digest,
            "normalized_arguments_digest": candidate.normalized_arguments_digest,
            "tool_fact_kind": candidate.tool_fact_kind.value,
            "accept_idempotency_key": candidate.accept_idempotency_key,
            "semantic_input_digest": candidate.semantic_input_digest,
        },
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
    return event_log_store.append_event(
        transaction,
        _tool_event_request(
            candidate,
            event_id=event_id,
            event_type=_EVENT_TYPE_TOOL_CALL_GOVERNED,
            policy_decision=_policy_decision_json(candidate.policy_decision),
            reason=_policy_reason_json(candidate.policy_decision),
            payload={
                "session_id": candidate.session_id,
                "run_id": candidate.run_id,
                "attempt_id": candidate.attempt_id,
                "execution_id": candidate.execution_id,
                "iteration_id": candidate.iteration_id,
                "tool_call_id": candidate.tool_call_id,
                "tool_name": candidate.tool_name,
                "tool_fact_kind": candidate.tool_fact_kind.value,
                "tool_call_requested_event_ref": _event_ref_json(
                    _event_ref_from_row(requested)
                ),
                "policy_decision": _policy_decision_json(
                    candidate.policy_decision
                ),
                "duplicate_key": candidate.duplicate_key,
                "duplicate_decision": (
                    candidate.duplicate_decision.value
                    if candidate.duplicate_decision is not None
                    else None
                ),
                "reuse_prior_event_refs": [
                    _event_ref_json(ref)
                    for ref in candidate.reuse_prior_event_refs
                ],
                "tool_idempotency_key": candidate.tool_idempotency_key,
                "diagnostic_refs": [
                    _diagnostic_ref_json(ref) for ref in candidate.diagnostic_refs
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
    payload_ref = candidate.payload_ref.payload_ref if candidate.payload_ref else None
    payload_digest = (
        candidate.payload_ref.payload_digest if candidate.payload_ref else None
    )
    return event_log_store.append_event(
        transaction,
        _tool_event_request(
            candidate,
            event_id=event_id,
            event_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            policy_decision=_policy_decision_json(candidate.policy_decision),
            reason=_policy_reason_json(candidate.policy_decision),
            payload={
                "session_id": candidate.session_id,
                "run_id": candidate.run_id,
                "attempt_id": candidate.attempt_id,
                "execution_id": candidate.execution_id,
                "iteration_id": candidate.iteration_id,
                "tool_call_id": candidate.tool_call_id,
                "tool_name": candidate.tool_name,
                "tool_fact_kind": candidate.tool_fact_kind.value,
                "tool_schema_digest": candidate.tool_schema_digest,
                "tool_identity_digest": candidate.tool_identity_digest,
                "normalized_arguments_digest": candidate.normalized_arguments_digest,
                "outcome_digest": candidate.outcome_digest,
                "payload_digest": candidate.payload_digest,
                "payload_ref": _payload_ref_json(candidate.payload_ref),
                "truncation": _truncation_json(candidate.truncation),
                "duplicate_key": candidate.duplicate_key,
                "duplicate_decision": (
                    candidate.duplicate_decision.value
                    if candidate.duplicate_decision is not None
                    else None
                ),
                "policy_decision": _policy_decision_json(
                    candidate.policy_decision
                ),
                "tool_idempotency_key": candidate.tool_idempotency_key,
                "diagnostic_refs": [
                    _diagnostic_ref_json(ref) for ref in candidate.diagnostic_refs
                ],
                "tool_call_requested_event_ref": _event_ref_json(
                    _event_ref_from_row(requested)
                ),
                "tool_call_governed_event_ref": (
                    _event_ref_json(_event_ref_from_row(governed))
                    if governed is not None
                    else None
                ),
                "accept_idempotency_key": candidate.accept_idempotency_key,
                "semantic_input_digest": candidate.semantic_input_digest,
            },
            payload_ref=payload_ref,
            payload_digest=payload_digest,
        ),
    ).row


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
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        attempt_id=candidate.attempt_id,
        execution_id=candidate.execution_id,
        event_type=event_type,
        occurred_at=datetime.now(UTC),
        actor=_TOOL_ACCEPT_EVENT_ACTOR,
        source=_TOOL_ACCEPT_EVENT_SOURCE,
        client_request_id=None,
        idempotency_key=candidate.accept_idempotency_key,
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
        or candidate.policy_decision.kind is not ToolPolicyDecisionKind.ALLOW
        or candidate.duplicate_decision is not None
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
        reuse_prior_event_refs=candidate.reuse_prior_event_refs,
        diagnostic_refs=candidate.diagnostic_refs,
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

    if candidate.outcome_digest is not None:
        return candidate.outcome_digest
    return candidate.semantic_input_digest


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
        diagnostic_refs=candidate.diagnostic_refs,
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


def _validate_common_candidate_fields(candidate: ToolFactAcceptCandidate) -> None:
    """校验 candidate 所有 fact kind 共享的必填字段。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: 字段缺失或 digest 非法时抛出。
    """

    for field_name, value in (
        ("session_id", candidate.session_id),
        ("run_id", candidate.run_id),
        ("attempt_id", candidate.attempt_id),
        ("execution_id", candidate.execution_id),
        ("iteration_id", candidate.iteration_id),
        ("tool_call_id", candidate.tool_call_id),
        ("tool_name", candidate.tool_name),
        ("accept_idempotency_key", candidate.accept_idempotency_key),
    ):
        _require_non_empty_text(value, field_name=field_name)
    _require_sha256_digest(
        candidate.tool_schema_digest, field_name="tool_schema_digest"
    )
    _require_sha256_digest(
        candidate.tool_identity_digest, field_name="tool_identity_digest"
    )
    _require_sha256_digest(
        candidate.normalized_arguments_digest,
        field_name="normalized_arguments_digest",
    )
    _require_sha256_digest(
        candidate.semantic_input_digest, field_name="semantic_input_digest"
    )
    _require_optional_sha256_digest(
        candidate.payload_digest, field_name="payload_digest"
    )
    if (
        candidate.payload_ref is not None
        and candidate.payload_digest != candidate.payload_ref.payload_digest
    ):
        raise ValueError("payload_digest must match payload_ref digest")
    _require_optional_non_empty_text(
        candidate.tool_idempotency_key, field_name="tool_idempotency_key"
    )
    if not isinstance(candidate.policy_decision, ToolPolicyDecision):
        raise ValueError("policy_decision must be ToolPolicyDecision")
    if not isinstance(candidate.tool_fact_kind, ToolFactKind):
        raise ValueError("tool_fact_kind must be ToolFactKind")


def _validate_duplicate_fields(candidate: ToolFactAcceptCandidate) -> None:
    """校验 duplicate governance 字段组合。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: duplicate decision 与 duplicate key 组合非法时抛出。
    """

    _require_optional_non_empty_text(candidate.duplicate_key, field_name="duplicate_key")
    if candidate.duplicate_decision is None:
        return
    if not isinstance(candidate.duplicate_decision, DuplicateDecisionKind):
        raise ValueError("duplicate_decision must be DuplicateDecisionKind")
    if (
        candidate.duplicate_decision
        in (
            DuplicateDecisionKind.REUSE,
            DuplicateDecisionKind.HINT,
            DuplicateDecisionKind.REQUIRE_JUSTIFICATION,
            DuplicateDecisionKind.HARD_STOP,
        )
        and candidate.duplicate_key is None
    ):
        raise ValueError("duplicate decision requires duplicate_key")


def _validate_reuse_candidate(candidate: ToolFactAcceptCandidate) -> None:
    """校验 reuse 工具事实候选。

    :param candidate: 工具事实候选。
    :returns: ``None``。
    :raises ValueError: reuse 字段不满足 canonical 语义时抛出。
    """

    if candidate.duplicate_key is None:
        raise ValueError("reuse requires duplicate_key")
    if candidate.duplicate_decision is not DuplicateDecisionKind.REUSE:
        raise ValueError("reuse requires duplicate_decision=reuse")
    if not candidate.reuse_prior_event_refs:
        raise ValueError("reuse requires prior event refs")
    if candidate.payload_ref is not None or candidate.payload_digest is not None:
        raise ValueError("reuse must not carry new result payload")


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


def _validate_reserved_name_conflicts(
    bundle: ToolBundle, policy: FrameworkToolPolicyView
) -> None:
    """校验业务工具没有占用 framework 预留名。

    :param bundle: 业务工具集合。
    :param policy: framework tool policy view。
    :returns: ``None``。
    :raises ValueError: 业务工具名占用预留名时抛出。
    """

    reserved = frozenset(
        tool_name.value for tool_name in policy.reserved_framework_tool_names
    )
    for definition in bundle.definitions:
        if definition.name in reserved:
            raise ValueError(
                "business ToolBundle contains reserved framework tool name:"
                f" {definition.name}"
            )


def _definitions_by_name(
    definitions: list[ToolDefinition],
) -> dict[str, ToolDefinition]:
    """按工具名索引工具声明并拒绝重复名称。

    :param definitions: effective 工具声明列表。
    :returns: 按名称索引的声明字典。
    :raises ValueError: 出现重复工具名时抛出。
    """

    result: dict[str, ToolDefinition] = {}
    for definition in definitions:
        if definition.name in result:
            raise ValueError(f"duplicate effective tool name: {definition.name}")
        result[definition.name] = definition
    return result


def _business_bundle_digest(bundle: ToolBundle) -> str:
    """计算业务 bundle 诊断摘要。

    :param bundle: 业务工具集合。
    :returns: Host canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "definitions": [
                _tool_definition_digest_json(definition)
                for definition in bundle.definitions
            ]
        }
    )


def _tool_schemas_digest(tool_schemas: tuple[ToolSchema, ...]) -> str:
    """计算 effective schema 诊断摘要。

    :param tool_schemas: effective schema 元组。
    :returns: Host canonical sha256 digest。
    """

    return sha256_digest_json(
        {"tool_schemas": [_tool_schema_json(schema) for schema in tool_schemas]}
    )


def _tool_definition_digest_json(definition: ToolDefinition) -> JsonValue:
    """把工具声明投影为 digest JSON。

    :param definition: 工具声明。
    :returns: 可用于 canonical digest 的 JSON 值。
    """

    return {
        "name": definition.name,
        "schema": _tool_schema_json(definition.schema),
        "truncate": _truncate_spec_json(definition.truncate),
        "tags": list(definition.tags),
    }


def _tool_schema_json(schema: ToolSchema) -> JsonValue:
    """把 ToolSchema 投影为 digest JSON。

    :param schema: 工具 schema。
    :returns: JSON 形态 schema。
    """

    return {
        "type": schema.type,
        "function": {
            "name": schema.function.name,
            "description": schema.function.description,
            "parameters": _parameters_json(schema.function.parameters),
        },
    }


def _parameters_json(parameters: ToolParametersSchema) -> JsonValue:
    """把工具参数 schema 投影为 digest JSON。

    :param parameters: 工具参数 schema。
    :returns: JSON 形态参数 schema。
    """

    result: dict[str, JsonValue] = {
        "type": parameters.type,
        "properties": parameters.properties,
        "required": list(parameters.required),
    }
    if parameters.additional_properties is not None:
        result["additionalProperties"] = parameters.additional_properties
    return result


def _truncate_spec_json(spec: ToolTruncateSpec | None) -> JsonValue:
    """把截断声明投影为 digest JSON。

    :param spec: 截断声明；无声明时为 ``None``。
    :returns: JSON 形态截断声明。
    """

    if spec is None:
        return None
    return {
        "enabled": spec.enabled,
        "strategy": spec.strategy,
        "limits": spec.limits,
        "target_field": spec.target_field,
        "field_path": list(spec.field_path) if spec.field_path is not None else None,
        "ttl_seconds": spec.ttl_seconds,
    }


__all__ = [
    "DefaultToolRuntimeFactory",
    "DefaultHostToolFactAcceptPort",
    "DuplicateDecision",
    "DuplicateDecisionKind",
    "DuplicateGovernancePort",
    "EffectiveToolBundle",
    "EffectiveToolBundleBuildRequest",
    "EffectiveToolBundleBuilder",
    "FrameworkToolInjector",
    "HostEventRef",
    "HostPayloadRef",
    "HostToolFactAcceptPort",
    "ToolAcceptRejectReason",
    "ToolAcceptRetryPolicy",
    "ToolDispatcher",
    "ToolFactAcceptCandidate",
    "ToolFactAcceptResult",
    "ToolFactAcceptTimedOut",
    "ToolFactAcceptedAck",
    "ToolFactKind",
    "ToolFactRejectedAck",
    "ToolPolicyDecision",
    "ToolPolicyDecisionKind",
    "ToolRuntimeBuildRequest",
    "ToolRuntimeFactory",
    "ToolRuntimeHandle",
    "ToolRuntimePolicyPort",
    "ToolRuntimeUnsupportedExecutor",
    "ToolTraceDiagnosticEmitter",
    "ToolTraceDiagnosticRecord",
    "ToolTraceDiagnosticRef",
    "ToolTruncationFact",
    "TruncationAppliedOutcome",
    "TruncationPort",
]
