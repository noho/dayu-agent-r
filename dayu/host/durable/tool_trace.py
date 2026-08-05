"""Host Tool Trace hot projection durable helper。

本模块只维护 ``ToolTraceProjectionConsumer`` 的 hot JSON projection 行与内部
诊断查询。Tool Trace 是 committed EventLog 的派生 projection，不是 Host
恢复、resume、memory 或 Run 状态迁移真源。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_identity import SuccessfulRunnerResponseIdentity
from dayu.host._runner_call_manifest import (
    RunnerCallHotAtoms,
    RunnerCallHotDiagnostic,
    RunnerCallInputManifest,
    parse_runner_call_hot_payload,
    parse_runner_call_manifest,
)
from dayu.host.durable._validation import (
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.codec import canonical_json_dumps
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventLogRow, read_run_events_by_types_page
from dayu.host.durable.payload_resolution import resolve_json_payload
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_TOOL_TRACE_HOT,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, SQLiteScalar
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    parse_context_compacted_terminal_binding,
    parse_context_compaction_attempt_rejected_terminal_binding,
)

TOOL_TRACE_QUERY_MAX_LIMIT = 500
"""Tool Trace 内部查询单页最大行数。"""

_MIN_QUERY_LIMIT = 1
_MIN_EVENT_CURSOR = 0
_JSON_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"
_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_RUNNER_CALL_TRACE_EVENT_TYPE = "event_type"
_RUNNER_CALL_PROJECTION_ARTIFACT_REF = "runner_call_projection_artifact_ref"
_RUNNER_CALL_PROJECTION_ARTIFACT_DIGEST = "runner_call_projection_artifact_digest"
_TOOL_SCHEMA_SNAPSHOT_REF_PREFIX = "tool_schema_snapshot_ref:"
_TOOL_SCHEMA_SNAPSHOT_DIGEST_PREFIX = "tool_schema_snapshot_digest:"
_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE = 128
"""仅界定单次 SQLite keyset read I/O；correctness 由完整 exhaustion 与 cursor
不变量拥有，不得开放为 public config。"""
_COMPACTOR_TERMINAL_EVENT_TYPES = (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
)


class RunnerCallReconstructionStatus(StrEnum):
    """Runner-call reconstruction signal 状态。"""

    COMPLETE = "complete"
    LIMITED_SIGNAL = "limited_signal"
    MISMATCH = "mismatch"


class RunnerCallReconstructionDiagnosticReason(StrEnum):
    """Runner-call reconstruction diagnostic reason 封闭枚举。"""

    MISSING_RUNNER_CALL_MANIFEST = "missing_runner_call_manifest"
    MISSING_PROJECTION_ARTIFACT = "missing_projection_artifact"
    MISSING_TOOL_CALL_ARGUMENTS_ATOM = "missing_tool_call_arguments_atom"
    MISSING_SEMANTIC_QUERY_ATOM = "missing_semantic_query_atom"
    MISSING_COMPACTOR_MANIFEST = "missing_compactor_manifest"
    MISSING_MEMORY_SNAPSHOT_BODY = "missing_memory_snapshot_body"
    UNSUPPORTED_PROJECTOR_VERSION = "unsupported_projector_version"
    MESSAGE_COUNT_MISMATCH = "message_count_mismatch"
    ROLE_SEQUENCE_DIGEST_MISMATCH = "role_sequence_digest_mismatch"
    INPUT_PROJECTION_DIGEST_MISMATCH = "input_projection_digest_mismatch"
    PAYLOAD_DIGEST_MISMATCH = "payload_digest_mismatch"
    UNRESOLVABLE_REF = "unresolvable_ref"
    PROVIDER_SPECIFIC_ATOM_DEFERRED = "provider_specific_atom_deferred"


class RunnerCallReconstructionMissingAtomKind(StrEnum):
    """Runner-call reconstruction 缺失 durable atom kind。"""

    TOOL_CALL_ARGUMENTS = "tool_call_arguments"
    SEMANTIC_QUERY = "semantic_query"
    RUNNER_CALL_MANIFEST = "runner_call_manifest"
    COMPACTOR_MANIFEST = "compactor_manifest"
    PROJECTION_ARTIFACT = "projection_artifact"
    MEMORY_SNAPSHOT_BODY = "memory_snapshot_body"


class RunnerCallReconstructionMissingRefKind(StrEnum):
    """Runner-call reconstruction 缺失 ref kind。"""

    PAYLOAD_REF = "payload_ref"
    ARTIFACT_REF = "artifact_ref"
    EVENT_REF = "event_ref"
    CURSOR_REF = "cursor_ref"


class RunnerCallReconstructionConsumerBoundary(StrEnum):
    """Runner-call reconstruction diagnostic consumer boundary。"""

    TOOL_TRACE_QUERY = "tool_trace_query"
    ANALYZER_FIXTURE = "analyzer_fixture"
    COMPACT_EVIDENCE_PROJECTION = "compact_evidence_projection"
    PUBLIC_SMOKE = "public_smoke"


class ToolTraceHotRowWriteStatus(StrEnum):
    """Tool Trace hot row 写入结果。"""

    INSERTED = "inserted"
    DUPLICATE = "duplicate"


class CompactorResponseDisposition(StrEnum):
    """公开 compactor response terminal disposition。"""

    ACCEPTED = "accepted"
    ATTEMPT_REJECTED = "attempt_rejected"


class CompactorResponseResolutionError(HostDurableError):
    """compactor canonical terminal 解析或绑定失败。"""


@dataclass(frozen=True, slots=True)
class ToolTraceHotRow:
    """Tool Trace hot projection row。

    :param trace_id: projection row 主键，当前等于 source ``event_id``。
    :param event_id: source EventLog id。
    :param event_sequence: source EventLog sequence。
    :param event_type: source EventLog event type。
    :param event_class: source EventLog event class。
    :param session_id: source Session id。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param tool_call_id: 可选工具调用 id。
    :param tool_name: 可选工具名。
    :param provider_request_id: 可选 provider request id。
    :param diagnostic_ref: 可选主诊断 ref。
    :param normalized_arguments_digest: 可选 normalized arguments digest。
    :param semantic_input_digest: 可选 semantic input digest。
    :param result_digest: 可选结果 digest。
    :param payload_ref: 可选 source payload ref。
    :param payload_digest: 可选 source payload digest。
    :param policy_decision_json: 可选 policy decision canonical JSON 文本。
    :param trace_summary: hot summary JSON object。
    :param cold_trace_ref: 可选 cold JSONL line ref。
    :param cold_trace_digest: 可选 cold JSONL line digest。
    :param projected_at: 投影写入 UTC timestamp 文本。
    :param updated_at: 投影更新时间 UTC timestamp 文本。
    """

    trace_id: str
    event_id: str
    event_sequence: int
    event_type: str
    event_class: str
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    tool_call_id: str | None
    tool_name: str | None
    provider_request_id: str | None
    diagnostic_ref: str | None
    normalized_arguments_digest: str | None
    semantic_input_digest: str | None
    result_digest: str | None
    payload_ref: str | None
    payload_digest: str | None
    policy_decision_json: str | None
    trace_summary: Mapping[str, JsonValue]
    cold_trace_ref: str | None
    cold_trace_digest: str | None
    projected_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ToolTraceHotRowWriteResult:
    """Tool Trace hot row 写入结果。

    :param status: 写入状态。
    :param row: 新写入或已存在的 hot row。
    """

    status: ToolTraceHotRowWriteStatus
    row: ToolTraceHotRow


@dataclass(frozen=True, slots=True)
class ToolTraceQueryPage:
    """Tool Trace 内部查询分页结果。

    :param rows: 当前页 hot rows。
    :param next_event_sequence: 下一次查询可使用的 event sequence cursor。
    :param has_more: 是否存在下一页。
    """

    rows: tuple[ToolTraceHotRow, ...]
    next_event_sequence: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class ProjectorMetadataSummary:
    """Runner-call projector metadata read-model 摘要。

    :param projector_metadata_id: manifest 内 projector metadata 引用 id。
    :param projector_id: projector 稳定逻辑 id。
    :param projector_schema_version: projector 输出契约版本。
    :param projector_digest: projector contract / configuration digest。
    :param purpose: projector 业务目的摘要。
    """

    projector_metadata_id: str
    projector_id: str
    projector_schema_version: str
    projector_digest: str
    purpose: str


@dataclass(frozen=True, slots=True)
class RunnerCallReconstructionDiagnostic:
    """Runner-call reconstruction typed diagnostic。

    :param status: reconstruction 状态。
    :param reason: 非 complete 状态下的封闭原因。
    :param missing_atom_kind: 可选缺失 durable atom kind。
    :param missing_ref_kind: 可选缺失 ref kind。
    :param missing_ref: 可选缺失 ref 标签。
    :param observed_count: mismatch 或 limited signal 观察到的数量。
    :param expected_count: mismatch 期望数量。
    :param observed_digest: mismatch 或 limited signal 观察到的 digest。
    :param expected_digest: mismatch 期望 digest。
    :param consumer_boundary: diagnostic 消费边界。
    """

    status: RunnerCallReconstructionStatus
    reason: RunnerCallReconstructionDiagnosticReason | None
    missing_atom_kind: RunnerCallReconstructionMissingAtomKind | None
    missing_ref_kind: RunnerCallReconstructionMissingRefKind | None
    missing_ref: str | None
    observed_count: int | None
    expected_count: int | None
    observed_digest: str | None
    expected_digest: str | None
    consumer_boundary: RunnerCallReconstructionConsumerBoundary


@dataclass(frozen=True, slots=True)
class RunnerCallReconstructionSignal:
    """Tool Trace runner-call reconstruction read-model signal。

    :param event_id: source EventLog id。
    :param event_sequence: source EventLog sequence。
    :param session_id: source Session id。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param runner_call_index: Host runner-call index。
    :param runner_call_kind: runner-call kind。
    :param runner_call_trigger_reason: runner-call trigger reason。
    :param iteration_id: 可选 Engine iteration id。
    :param manifest_ref: runner-call manifest descriptor ref。
    :param manifest_digest: runner-call manifest digest。
    :param message_count: runner-call message count summary。
    :param role_sequence_digest: runner-call role sequence digest。
    :param input_projection_digest: runner-call source summary digest。
    :param projector_metadata_summary: projector metadata summary 元组。
    :param diagnostic: typed reconstruction diagnostic。
    """

    event_id: str
    event_sequence: int
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    runner_call_index: int | None
    runner_call_kind: str | None
    runner_call_trigger_reason: str | None
    iteration_id: str | None
    manifest_ref: str | None
    manifest_digest: str | None
    message_count: int | None
    role_sequence_digest: str | None
    input_projection_digest: str | None
    projector_metadata_summary: tuple[ProjectorMetadataSummary, ...]
    diagnostic: RunnerCallReconstructionDiagnostic


@dataclass(frozen=True, slots=True)
class RunnerCallReconstructionSignalPage:
    """Runner-call reconstruction signal 分页结果。

    :param signals: 当前页 signal。
    :param next_event_sequence: 下一次查询可使用的 event sequence cursor。
    :param has_more: 是否存在下一页。
    """

    signals: tuple[RunnerCallReconstructionSignal, ...]
    next_event_sequence: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class ToolTraceResolvedJsonPayload:
    """Tool Trace resolver 读取出的 JSON payload。

    :param payload_ref: payload descriptor ref。
    :param payload_digest: descriptor 中记录的 payload digest。
    :param payload_size_bytes: descriptor 中记录的 payload 字节数。
    :param media_type: payload media type。
    :param payload: 已校验 digest 的 JSON object。
    """

    payload_ref: str
    payload_digest: str
    payload_size_bytes: int
    media_type: str | None
    payload: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RunnerCallResolvedProjection:
    """Runner-call reconstruction resolver 结果。

    :param signal: Tool Trace runner-call signal。
    :param manifest: runner-call manifest JSON payload。
    :param runner_input_projection: LLM-facing runner input projection JSON payload。
    :param selected_tool_schema_snapshot: selected tool schema full JSON snapshot；
        本轮无工具 schema 时为 ``None``。
    :param compactor_response_identity: compactor proposal 对应的 canonical
        terminal response identity；普通 runner call 或完整扫描后未观察到 matching
        terminal 时为 ``None``。
    """

    signal: RunnerCallReconstructionSignal
    manifest: ToolTraceResolvedJsonPayload
    runner_input_projection: ToolTraceResolvedJsonPayload
    selected_tool_schema_snapshot: ToolTraceResolvedJsonPayload | None
    compactor_response_identity: ResolvedCompactorResponseIdentity | None


@dataclass(frozen=True, slots=True)
class ResolvedCompactorResponseIdentity:
    """Tool Trace resolver 公开的 compactor terminal response identity。

    :param disposition: accepted 或 attempt-rejected terminal。
    :param terminal_event_id: canonical terminal event id。
    :param terminal_event_sequence: canonical terminal event sequence。
    :param compaction_operation_id: manifest 与 terminal 同源 operation id。
    :param compaction_attempt_number: manifest 与 terminal 同源 attempt 序号。
    :param proposal_manifest_ref: exact proposal manifest ref。
    :param proposal_manifest_digest: exact proposal manifest digest。
    :param successful_response_identity: 实际成功 Runner response identity；
        no-success rejection 时为 ``None``。
    """

    disposition: CompactorResponseDisposition
    terminal_event_id: str
    terminal_event_sequence: int
    compaction_operation_id: str
    compaction_attempt_number: int
    proposal_manifest_ref: str
    proposal_manifest_digest: str
    successful_response_identity: SuccessfulRunnerResponseIdentity | None

    def __post_init__(self) -> None:
        """校验公开 response projection 的封闭 typed shape。

        :returns: 无返回值。
        :raises TypeError: disposition 或 response identity 类型非法时抛出。
        :raises ValueError: identity 文本为空或 sequence/attempt 非正时抛出。
        """

        if not isinstance(self.disposition, CompactorResponseDisposition):
            raise TypeError("disposition must be CompactorResponseDisposition")
        for field_name, value in (
            ("terminal_event_id", self.terminal_event_id),
            ("compaction_operation_id", self.compaction_operation_id),
            ("proposal_manifest_ref", self.proposal_manifest_ref),
            ("proposal_manifest_digest", self.proposal_manifest_digest),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be str")
            if value.strip() == "":
                raise ValueError(f"{field_name} must be non-empty")
        if isinstance(self.terminal_event_sequence, bool) or not isinstance(
            self.terminal_event_sequence,
            int,
        ):
            raise TypeError("terminal_event_sequence must be int")
        if self.terminal_event_sequence <= 0:
            raise ValueError("terminal_event_sequence must be positive")
        if isinstance(self.compaction_attempt_number, bool) or not isinstance(
            self.compaction_attempt_number,
            int,
        ):
            raise TypeError("compaction_attempt_number must be int")
        if self.compaction_attempt_number <= 0:
            raise ValueError("compaction_attempt_number must be positive")
        if self.successful_response_identity is not None and not isinstance(
            self.successful_response_identity,
            SuccessfulRunnerResponseIdentity,
        ):
            raise TypeError(
                "successful_response_identity must be SuccessfulRunnerResponseIdentity or None"
            )
        if (
            self.disposition is CompactorResponseDisposition.ACCEPTED
            and self.successful_response_identity is None
        ):
            raise ValueError(
                "accepted compactor response requires successful response identity"
            )


@dataclass(frozen=True, slots=True)
class _ValidatedRunnerCallContract:
    """Tool Trace 查询边界已完整校验的 runner-call contract。

    :param hot_payload: source EventLog 的 typed hot atoms。
    :param manifest: durable resolver 与 full-manifest owner 已校验的 manifest。
    """

    hot_payload: RunnerCallHotAtoms
    manifest: RunnerCallInputManifest


@dataclass(frozen=True, slots=True)
class ToolTraceResolvedRowPayloads:
    """Tool Trace hot row resolver 结果。

    :param row: Tool Trace hot row。
    :param source_event_payload: source EventLog hot payload。
    :param descriptor_payload: row ``payload_ref`` 指向的 JSON payload；没有
        payload ref 时为 ``None``。
    """

    row: ToolTraceHotRow
    source_event_payload: Mapping[str, JsonValue]
    descriptor_payload: ToolTraceResolvedJsonPayload | None


def resolve_runner_call_projection_from_signal(
    transaction: HostTransaction,
    signal: RunnerCallReconstructionSignal,
) -> RunnerCallResolvedProjection:
    """从 runner-call signal 解析 manifest、input projection 与 schema snapshot。

    :param transaction: 调用方提供的 Host durable transaction。
    :param signal: ``read_runner_call_reconstruction_signals_by_run`` 返回的
        runner-call signal。
    :returns: 已校验 digest 的 runner-call resolved projection。
    :raises HostDurableError: ref 缺失、payload 不存在、payload 不是 JSON object
        或 digest 校验失败时抛出。
    """

    if signal.manifest_ref is None:
        raise HostDurableError("runner-call signal has no manifest_ref")
    if signal.manifest_digest is None:
        raise HostDurableError("runner-call signal has no manifest_digest")
    manifest = read_tool_trace_json_payload(
        transaction,
        signal.manifest_ref,
        expected_digest=signal.manifest_digest,
    )
    typed_manifest = _typed_manifest_from_signal(
        transaction,
        signal=signal,
        resolved_manifest=manifest,
    )
    projection_ref = _json_optional_text(
        manifest.payload,
        _RUNNER_CALL_PROJECTION_ARTIFACT_REF,
    )
    projection_digest = _json_optional_text(
        manifest.payload,
        _RUNNER_CALL_PROJECTION_ARTIFACT_DIGEST,
    )
    if projection_ref is None:
        raise HostDurableError("runner-call manifest has no projection artifact ref")
    if projection_digest is None:
        raise HostDurableError("runner-call manifest has no projection artifact digest")
    projection = read_tool_trace_json_payload(
        transaction,
        projection_ref,
        expected_digest=projection_digest,
    )
    return RunnerCallResolvedProjection(
        signal=signal,
        manifest=manifest,
        runner_input_projection=projection,
        selected_tool_schema_snapshot=_resolve_selected_tool_schema_snapshot(
            transaction,
            manifest.payload,
        ),
        compactor_response_identity=_resolve_compactor_response_identity(
            transaction,
            typed_manifest,
            proposal_manifest_ref=manifest.payload_ref,
            proposal_manifest_digest=manifest.payload_digest,
        ),
    )


def _typed_manifest_from_signal(
    transaction: HostTransaction,
    *,
    signal: RunnerCallReconstructionSignal,
    resolved_manifest: ToolTraceResolvedJsonPayload,
) -> RunnerCallInputManifest:
    """从 signal 的 canonical event 与 descriptor 恢复 typed manifest。

    :param transaction: 调用方持有的 Host read transaction。
    :param signal: 待复核的 runner-call signal。
    :param resolved_manifest: 已通过 ref/digest 校验的 manifest payload。
    :returns: shared manifest owner 完整校验后的 typed manifest。
    :raises HostDurableError: signal、hot atoms 或 manifest graph 任一不一致时抛出。
    """

    hot_payload = parse_runner_call_hot_payload(
        _read_event_payload(transaction, signal.event_id)
    )
    if (
        signal.session_id != hot_payload.session_id
        or signal.run_id != hot_payload.host_run_id
        or signal.attempt_id != hot_payload.attempt_id
        or signal.execution_id != hot_payload.execution_id
        or signal.runner_call_index != hot_payload.runner_call_index
        or signal.runner_call_kind != hot_payload.runner_call_kind
        or signal.runner_call_trigger_reason
        != hot_payload.runner_call_trigger_reason
        or signal.iteration_id != hot_payload.iteration_id
        or signal.manifest_ref != hot_payload.manifest_payload_ref
        or signal.manifest_digest != hot_payload.manifest_digest
        or signal.message_count != hot_payload.message_count
        or signal.role_sequence_digest != hot_payload.role_sequence_digest
        or signal.input_projection_digest != hot_payload.input_projection_digest
    ):
        raise HostDurableError("runner-call signal and canonical hot identity mismatch")
    return parse_runner_call_manifest(
        resolved_manifest.payload,
        hot_payload=hot_payload,
    )


def _resolve_compactor_response_identity(
    transaction: HostTransaction,
    manifest: RunnerCallInputManifest,
    *,
    proposal_manifest_ref: str,
    proposal_manifest_digest: str,
) -> ResolvedCompactorResponseIdentity | None:
    """完整扫描 parent Host Run 并解析唯一 matching compactor terminal。

    :param transaction: 调用方持有的同一个 Host read transaction。
    :param manifest: shared owner 完整校验后的 runner-call manifest。
    :param proposal_manifest_ref: signal/hot owner 校验过的 manifest descriptor ref。
    :param proposal_manifest_digest: signal/hot owner 校验过的 manifest body digest。
    :returns: matching terminal response identity；ordinary call 或完整 exhaustion 后
        无 matching terminal 时为 ``None``。
    :raises CompactorResponseResolutionError: page/cursor、canonical payload、binding
        或唯一性不变量损坏时抛出。
    """

    compactor_identity = manifest.compactor_identity
    if compactor_identity is None:
        return None
    cursor = 0
    resolved: ResolvedCompactorResponseIdentity | None = None
    while True:
        try:
            page = read_run_events_by_types_page(
                transaction,
                run_id=compactor_identity.parent_host_run_id,
                event_types=_COMPACTOR_TERMINAL_EVENT_TYPES,
                after_event_sequence=cursor,
                limit=_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE,
            )
        except HostDurableError as exc:
            raise CompactorResponseResolutionError(
                "compactor terminal page read failed"
            ) from exc
        if len(page) > _COMPACTOR_TERMINAL_SCAN_PAGE_SIZE:
            raise CompactorResponseResolutionError(
                "compactor terminal page exceeds requested size"
            )
        previous_sequence = cursor
        for row in page:
            if row.event_sequence <= previous_sequence:
                raise CompactorResponseResolutionError(
                    "compactor terminal keyset cursor did not advance"
                )
            previous_sequence = row.event_sequence
            candidate = _resolved_compactor_response_from_row(
                row,
                manifest=manifest,
                proposal_manifest_ref=proposal_manifest_ref,
                proposal_manifest_digest=proposal_manifest_digest,
            )
            if candidate is None:
                continue
            if resolved is not None:
                raise CompactorResponseResolutionError(
                    "compactor manifest has duplicate canonical terminals"
                )
            resolved = candidate
        if len(page) < _COMPACTOR_TERMINAL_SCAN_PAGE_SIZE:
            return resolved
        if previous_sequence <= cursor:
            raise CompactorResponseResolutionError(
                "compactor terminal full page cursor did not advance"
            )
        cursor = previous_sequence


def _resolved_compactor_response_from_row(
    row: EventLogRow,
    *,
    manifest: RunnerCallInputManifest,
    proposal_manifest_ref: str,
    proposal_manifest_digest: str,
) -> ResolvedCompactorResponseIdentity | None:
    """严格解析单条 canonical terminal 并判断其是否匹配 manifest。

    :param row: parent Host Run 的 canonical terminal row。
    :param manifest: 当前 compactor proposal typed manifest。
    :param proposal_manifest_ref: 当前 manifest descriptor ref。
    :param proposal_manifest_digest: 当前 manifest body digest。
    :returns: exact matching response；无关联 sibling terminal 返回 ``None``。
    :raises CompactorResponseResolutionError: payload、manifest binding 或 Engine
        response identity 不一致时抛出。
    """

    compactor_identity = manifest.compactor_identity
    if compactor_identity is None:
        raise CompactorResponseResolutionError(
            "ordinary runner manifest cannot resolve compactor terminal"
        )
    try:
        payload = _json_object_from_text(row.payload_json)
        if row.event_type == CONTEXT_COMPACTED:
            binding = parse_context_compacted_terminal_binding(payload)
            disposition = CompactorResponseDisposition.ACCEPTED
        elif row.event_type == CONTEXT_COMPACTION_ATTEMPT_REJECTED:
            binding = parse_context_compaction_attempt_rejected_terminal_binding(
                payload
            )
            disposition = CompactorResponseDisposition.ATTEMPT_REJECTED
        else:
            raise ValueError("unsupported compactor terminal event type")
    except (TypeError, ValueError, HostDurableError) as exc:
        raise CompactorResponseResolutionError(
            "compactor canonical terminal payload is malformed"
        ) from exc
    operation_matches = (
        binding.operation_id == compactor_identity.compaction_operation_id
        and binding.attempt_number
        == compactor_identity.compaction_attempt_number
    )
    manifest_matches = (
        binding.proposal_manifest_ref == proposal_manifest_ref
        and binding.proposal_manifest_digest == proposal_manifest_digest
    )
    if operation_matches != manifest_matches:
        raise CompactorResponseResolutionError(
            "compactor terminal manifest/operation/attempt binding mismatch"
        )
    if not operation_matches:
        return None
    response_identity = binding.successful_response_identity
    if (
        response_identity is not None
        and response_identity.runner_request_identity.run_id
        != compactor_identity.compactor_engine_run_id
    ):
        raise CompactorResponseResolutionError(
            "compactor terminal Engine run identity mismatch"
        )
    if binding.proposal_manifest_ref is None or binding.proposal_manifest_digest is None:
        raise CompactorResponseResolutionError(
            "matching compactor terminal has no proposal manifest binding"
        )
    return ResolvedCompactorResponseIdentity(
        disposition=disposition,
        terminal_event_id=row.event_id,
        terminal_event_sequence=row.event_sequence,
        compaction_operation_id=binding.operation_id,
        compaction_attempt_number=binding.attempt_number,
        proposal_manifest_ref=binding.proposal_manifest_ref,
        proposal_manifest_digest=binding.proposal_manifest_digest,
        successful_response_identity=response_identity,
    )


def resolve_tool_trace_hot_row_payloads(
    transaction: HostTransaction,
    row: ToolTraceHotRow,
) -> ToolTraceResolvedRowPayloads:
    """解析 Tool Trace row 的 source EventLog payload 与 descriptor payload。

    :param transaction: 调用方提供的 Host durable transaction。
    :param row: Tool Trace hot row。
    :returns: 已解析 payloads。若 row 没有 ``payload_ref``，descriptor payload
        为 ``None``。
    :raises HostDurableError: source event 或 descriptor payload 缺失、格式非法
        或 digest 校验失败时抛出。
    """

    source_event_payload = _read_event_payload(transaction, row.event_id)
    descriptor_ref, descriptor_digest = _descriptor_ref_from_row_or_payload(
        row,
        source_event_payload,
    )
    descriptor_payload = (
        None
        if descriptor_ref is None
        else _read_hot_row_descriptor_payload(
            transaction,
            descriptor_ref=descriptor_ref,
            descriptor_digest=descriptor_digest,
        )
    )
    return ToolTraceResolvedRowPayloads(
        row=row,
        source_event_payload=source_event_payload,
        descriptor_payload=descriptor_payload,
    )


def read_tool_trace_json_payload(
    transaction: HostTransaction,
    payload_ref: str,
    *,
    expected_digest: str,
) -> ToolTraceResolvedJsonPayload:
    """读取并校验 Tool Trace resolver 使用的 JSON payload descriptor。

    :param transaction: 调用方提供的 Host durable transaction。
    :param payload_ref: payload descriptor ref。
    :param expected_digest: 调用方持有的期望 digest。
    :returns: 已校验 digest 的 JSON payload。
    :raises HostDurableError: descriptor/payload 缺失、JSON 不是 object 或
        digest 不匹配时抛出。
    """

    resolved = resolve_json_payload(
        transaction,
        payload_ref=payload_ref,
        expected_digest=expected_digest,
    )
    descriptor = resolved.descriptor
    return ToolTraceResolvedJsonPayload(
        payload_ref=descriptor.payload_ref,
        payload_digest=descriptor.payload_digest,
        payload_size_bytes=descriptor.payload_size_bytes,
        media_type=descriptor.media_type,
        payload=resolved.payload,
    )


def _read_hot_row_descriptor_payload(
    transaction: HostTransaction,
    *,
    descriptor_ref: str,
    descriptor_digest: str | None,
) -> ToolTraceResolvedJsonPayload:
    """读取 Tool Trace hot row 声明的 descriptor payload。

    :param transaction: 调用方提供的 Host durable transaction。
    :param descriptor_ref: hot row/source event 声明的 descriptor ref。
    :param descriptor_digest: hot row/source event 声明的 digest。
    :returns: 已完成共享完整性校验的 JSON payload。
    :raises HostDurableError: digest 缺失或 descriptor payload 非法时抛出。
    """

    if descriptor_digest is None:
        raise HostDurableError("tool trace descriptor digest is missing")
    return read_tool_trace_json_payload(
        transaction,
        descriptor_ref,
        expected_digest=descriptor_digest,
    )


def _resolve_selected_tool_schema_snapshot(
    transaction: HostTransaction,
    manifest: Mapping[str, JsonValue],
) -> ToolTraceResolvedJsonPayload | None:
    """从 manifest 解析 selected tool schema snapshot payload。

    :param transaction: 调用方提供的 Host durable transaction。
    :param manifest: runner-call manifest JSON object。
    :returns: schema snapshot payload；本轮无工具时返回 ``None``。
    :raises HostDurableError: refs 字段格式非法或 payload 无法解析时抛出。
    """

    refs_value = manifest.get("tool_schema_snapshot_refs")
    if not isinstance(refs_value, list):
        raise HostDurableError("runner-call manifest tool_schema_snapshot_refs invalid")
    snapshot_ref: str | None = None
    snapshot_digest: str | None = None
    for item in refs_value:
        if not isinstance(item, str):
            raise HostDurableError("tool schema snapshot ref must be text")
        if item.startswith(_TOOL_SCHEMA_SNAPSHOT_REF_PREFIX):
            snapshot_ref = item.removeprefix(_TOOL_SCHEMA_SNAPSHOT_REF_PREFIX)
        elif item.startswith(_TOOL_SCHEMA_SNAPSHOT_DIGEST_PREFIX):
            snapshot_digest = item.removeprefix(_TOOL_SCHEMA_SNAPSHOT_DIGEST_PREFIX)
    if snapshot_ref is None:
        return None
    if snapshot_digest is None:
        raise HostDurableError("tool schema snapshot digest is missing")
    return read_tool_trace_json_payload(
        transaction,
        snapshot_ref,
        expected_digest=snapshot_digest,
    )


def _read_event_payload(
    transaction: HostTransaction,
    event_id: str,
) -> Mapping[str, JsonValue]:
    """读取 source EventLog hot payload。

    :param transaction: 调用方提供的 Host durable transaction。
    :param event_id: EventLog id。
    :returns: source event payload JSON object。
    :raises HostDurableError: event 缺失、payload 缺失或 JSON 非 object 时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT payload_json
        FROM {TABLE_EVENT_LOG}
        WHERE event_id = ?
        """,
        (event_id,),
    )
    if row is None:
        raise HostDurableError("tool trace source event is missing")
    payload_json = _require_text(row.get("payload_json"), field_name="payload_json")
    return _json_object_from_text(payload_json)


def _descriptor_ref_from_row_or_payload(
    row: ToolTraceHotRow,
    source_event_payload: Mapping[str, JsonValue],
) -> tuple[str | None, str | None]:
    """从 hot row 或 source payload 读取 payload descriptor ref/digest。

    :param row: Tool Trace hot row。
    :param source_event_payload: source EventLog payload。
    :returns: ``(payload_ref, payload_digest)``；无 descriptor 时二者为
        ``None``。
    :raises HostDurableError: payload_ref object 字段类型非法时抛出。
    """

    if row.payload_ref is not None:
        return row.payload_ref, row.payload_digest
    payload_ref_value = source_event_payload.get("payload_ref")
    if isinstance(payload_ref_value, Mapping):
        payload_mapping = cast(Mapping[str, JsonValue], payload_ref_value)
        return (
            _json_optional_text(payload_mapping, "payload_ref"),
            _json_optional_text(payload_mapping, "payload_digest"),
        )
    if payload_ref_value is not None:
        raise HostDurableError("tool trace source payload_ref must be object")
    return (
        _json_optional_text(source_event_payload, "terminal_summary_ref"),
        _json_optional_text(source_event_payload, "terminal_summary_digest"),
    )


def _json_optional_text(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取 JSON object 的可选文本字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 字段存在但不是文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise HostDurableError(f"tool trace payload {field_name} must be text")


def read_tool_trace_hot_row(
    transaction: HostTransaction, event_id: str
) -> ToolTraceHotRow | None:
    """按 source EventLog id 读取 Tool Trace hot row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param event_id: source EventLog id。
    :returns: 存在时返回 hot row，否则返回 ``None``。
    :raises HostDurableError: ``event_id`` 无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(event_id, field_name="event_id")
    row = transaction.fetchone(
        f"""
        SELECT
          trace_id,
          event_id,
          event_sequence,
          event_type,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          provider_request_id,
          diagnostic_ref,
          normalized_arguments_digest,
          semantic_input_digest,
          result_digest,
          payload_ref,
          payload_digest,
          policy_decision_json,
          trace_summary_json,
          cold_trace_ref,
          cold_trace_digest,
          projected_at,
          updated_at
        FROM {TABLE_HOST_TOOL_TRACE_HOT}
        WHERE event_id = ?
        """,
        (event_id,),
    )
    if row is None:
        return None
    return _hot_row_from_host_row(row)


def insert_tool_trace_hot_row_if_absent(
    transaction: HostTransaction, row: ToolTraceHotRow
) -> ToolTraceHotRowWriteResult:
    """写入 Tool Trace hot row；已存在时按 EventLog logical duplicate 处理。

    :param transaction: 调用方提供的 Host durable transaction。
    :param row: 待写入 hot row。
    :returns: 写入结果。
    :raises HostDurableError: 输入无效、既有 row 与 source identity 冲突或写入后无法读回时抛出。
    """

    _validate_hot_row(row)
    existing = read_tool_trace_hot_row(transaction, row.event_id)
    if existing is not None:
        if existing.event_sequence != row.event_sequence:
            raise HostDurableError("tool trace hot row conflicts with EventLog row")
        return ToolTraceHotRowWriteResult(
            status=ToolTraceHotRowWriteStatus.DUPLICATE,
            row=existing,
        )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_TOOL_TRACE_HOT} (
          trace_id,
          event_id,
          event_sequence,
          event_type,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          provider_request_id,
          diagnostic_ref,
          normalized_arguments_digest,
          semantic_input_digest,
          result_digest,
          payload_ref,
          payload_digest,
          policy_decision_json,
          trace_summary_json,
          cold_trace_ref,
          cold_trace_digest,
          projected_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.trace_id,
            row.event_id,
            row.event_sequence,
            row.event_type,
            row.event_class,
            row.session_id,
            row.run_id,
            row.attempt_id,
            row.execution_id,
            row.tool_call_id,
            row.tool_name,
            row.provider_request_id,
            row.diagnostic_ref,
            row.normalized_arguments_digest,
            row.semantic_input_digest,
            row.result_digest,
            row.payload_ref,
            row.payload_digest,
            row.policy_decision_json,
            canonical_json_dumps(row.trace_summary),
            row.cold_trace_ref,
            row.cold_trace_digest,
            row.projected_at,
            row.updated_at,
        ),
    )
    inserted = read_tool_trace_hot_row(transaction, row.event_id)
    if inserted is None:
        raise HostDurableError("tool trace hot row write failed")
    return ToolTraceHotRowWriteResult(
        status=ToolTraceHotRowWriteStatus.INSERTED,
        row=inserted,
    )


def read_tool_trace_by_run(
    transaction: HostTransaction,
    run_id: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 Run id 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: Run id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    return _query_page(
        transaction,
        where_sql="run_id = ?",
        parameters=(run_id,),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def read_tool_trace_page(
    transaction: HostTransaction,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """无过滤分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    return _query_page(
        transaction,
        where_sql="1 = 1",
        parameters=(),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def find_tool_trace_by_tool_call_id(
    transaction: HostTransaction,
    tool_call_id: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 tool call id 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param tool_call_id: 工具调用 id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(tool_call_id, field_name="tool_call_id")
    return _query_page(
        transaction,
        where_sql="tool_call_id = ?",
        parameters=(tool_call_id,),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def find_tool_trace_by_provider_request_id(
    transaction: HostTransaction,
    provider_request_id: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 provider request id 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param provider_request_id: provider request id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(provider_request_id, field_name="provider_request_id")
    return _query_page(
        transaction,
        where_sql="provider_request_id = ?",
        parameters=(provider_request_id,),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def find_tool_trace_by_diagnostic_ref(
    transaction: HostTransaction,
    diagnostic_ref: str,
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """按 diagnostic ref 分页读取 Tool Trace hot rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param diagnostic_ref: 诊断引用。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(diagnostic_ref, field_name="diagnostic_ref")
    return _query_page(
        transaction,
        where_sql=(
            "diagnostic_ref = ? OR EXISTS ("
            "SELECT 1 FROM json_each(trace_summary_json, '$."
            + _JSON_FIELD_DIAGNOSTIC_REFS
            + "') WHERE json_each.value = ?)"
        ),
        parameters=(diagnostic_ref, diagnostic_ref),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )


def read_runner_call_reconstruction_signals_by_run(
    transaction: HostTransaction,
    run_id: str,
    after_event_sequence: int,
    limit: int,
) -> RunnerCallReconstructionSignalPage:
    """按 Run id 读取 runner-call reconstruction signals。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: Run id。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回 signal 数上限，必须为正数且不超过模块上限。
    :returns: 按 ``event_sequence ASC`` 排列的 runner-call signal 页。
    :raises HostDurableError: 输入非法或 Tool Trace projection JSON 类型不符合契约时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    page = _query_page(
        transaction,
        where_sql="run_id = ? AND event_type = ?",
        parameters=(run_id, _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED),
        after_event_sequence=after_event_sequence,
        limit=limit,
    )
    return RunnerCallReconstructionSignalPage(
        signals=tuple(
            _runner_call_signal_from_hot_row(transaction, row) for row in page.rows
        ),
        next_event_sequence=page.next_event_sequence,
        has_more=page.has_more,
    )


def _query_page(
    transaction: HostTransaction,
    *,
    where_sql: str,
    parameters: tuple[SQLiteScalar, ...],
    after_event_sequence: int,
    limit: int,
) -> ToolTraceQueryPage:
    """执行 Tool Trace hot row 分页查询。

    :param transaction: 调用方提供的 Host durable transaction。
    :param where_sql: 不含 cursor 的 SQL WHERE 条件。
    :param parameters: WHERE 条件参数。
    :param after_event_sequence: 严格大于该 cursor 的 event sequence。
    :param limit: 返回行数上限。
    :returns: 查询页。
    :raises HostDurableError: 输入非法或 durable row 类型不符合预期时抛出。
    """

    _validate_query_page_input(after_event_sequence, limit)
    fetch_limit = limit + 1
    rows = transaction.fetchall(
        f"""
        SELECT
          trace_id,
          event_id,
          event_sequence,
          event_type,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          provider_request_id,
          diagnostic_ref,
          normalized_arguments_digest,
          semantic_input_digest,
          result_digest,
          payload_ref,
          payload_digest,
          policy_decision_json,
          trace_summary_json,
          cold_trace_ref,
          cold_trace_digest,
          projected_at,
          updated_at
        FROM {TABLE_HOST_TOOL_TRACE_HOT}
        WHERE event_sequence > ?
          AND ({where_sql})
        ORDER BY event_sequence ASC
        LIMIT ?
        """,
        (after_event_sequence, *parameters, fetch_limit),
    )
    page_rows = tuple(_hot_row_from_host_row(row) for row in rows[:limit])
    next_event_sequence = (
        page_rows[-1].event_sequence
        if len(page_rows) > 0
        else after_event_sequence
    )
    return ToolTraceQueryPage(
        rows=page_rows,
        next_event_sequence=next_event_sequence,
        has_more=len(rows) > limit,
    )


def _runner_call_signal_from_hot_row(
    transaction: HostTransaction,
    row: ToolTraceHotRow,
) -> RunnerCallReconstructionSignal:
    """把 hot row 转换为 typed runner-call reconstruction signal。

    :param transaction: 调用方当前 Host durable transaction。
    :param row: Tool Trace hot row。
    :returns: typed runner-call reconstruction signal。
    :raises HostDurableError: row 不是 runner-call signal 或 summary 类型非法时抛出。
    """

    summary = row.trace_summary
    event_type = _summary_required_text(summary, _RUNNER_CALL_TRACE_EVENT_TYPE)
    if event_type != _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED:
        raise HostDurableError("tool trace row is not runner-call signal")
    contract = _validated_runner_call_contract(transaction, row)
    hot_payload = contract.hot_payload
    return RunnerCallReconstructionSignal(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        session_id=row.session_id,
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        execution_id=row.execution_id,
        runner_call_index=hot_payload.runner_call_index,
        runner_call_kind=hot_payload.runner_call_kind,
        runner_call_trigger_reason=hot_payload.runner_call_trigger_reason,
        iteration_id=hot_payload.iteration_id,
        manifest_ref=hot_payload.manifest_payload_ref,
        manifest_digest=hot_payload.manifest_digest,
        message_count=hot_payload.message_count,
        role_sequence_digest=hot_payload.role_sequence_digest,
        input_projection_digest=hot_payload.input_projection_digest,
        projector_metadata_summary=_projector_metadata_summary_from_manifest(
            contract.manifest,
        ),
        diagnostic=_runner_call_diagnostic_from_hot(hot_payload.diagnostic),
    )


def _validated_runner_call_contract(
    transaction: HostTransaction,
    row: ToolTraceHotRow,
) -> _ValidatedRunnerCallContract:
    """从 source EventLog 与 manifest descriptor 构造完整 typed contract。

    :param transaction: 调用方当前 Host durable transaction。
    :param row: runner-call Tool Trace hot row。
    :returns: hot/manifest 均完成 owner 校验的 contract。
    :raises HostDurableError: source hot、row identity、descriptor integrity 或
        full manifest semantic graph 非法时抛出。
    """

    hot_payload = parse_runner_call_hot_payload(
        _read_event_payload(transaction, row.event_id)
    )
    if (
        row.session_id != hot_payload.session_id
        or row.run_id != hot_payload.host_run_id
        or row.attempt_id != hot_payload.attempt_id
        or row.execution_id != hot_payload.execution_id
        or row.payload_ref != hot_payload.manifest_payload_ref
        or row.payload_digest != hot_payload.manifest_digest
    ):
        raise HostDurableError("tool trace row and runner-call hot identity mismatch")
    resolved_manifest = read_tool_trace_json_payload(
        transaction,
        hot_payload.manifest_payload_ref,
        expected_digest=hot_payload.manifest_digest,
    )
    return _ValidatedRunnerCallContract(
        hot_payload=hot_payload,
        manifest=parse_runner_call_manifest(
            resolved_manifest.payload,
            hot_payload=hot_payload,
        ),
    )


def _projector_metadata_summary_from_manifest(
    manifest: RunnerCallInputManifest,
) -> tuple[ProjectorMetadataSummary, ...]:
    """从 typed validated manifest 重建 projector metadata summary。

    :param manifest: full-manifest owner 已校验的 typed manifest。
    :returns: typed projector metadata summary 元组。
    :raises: 无。
    """

    return tuple(
        ProjectorMetadataSummary(
            projector_metadata_id=metadata.projector_metadata_id,
            projector_id=metadata.projector_id,
            projector_schema_version=metadata.projector_schema_version,
            projector_digest=metadata.projector_digest,
            purpose=metadata.purpose,
        )
        for metadata in manifest.projector_metadata
    )


def _runner_call_diagnostic_from_hot(
    diagnostic: RunnerCallHotDiagnostic,
) -> RunnerCallReconstructionDiagnostic:
    """把 shared owner diagnostic 投影为 Tool Trace typed diagnostic。

    :param diagnostic: shared owner 已校验的 hot diagnostic。
    :returns: typed runner-call diagnostic。
    :raises HostDurableError: enum 文本不能投影到 Tool Trace contract 时抛出。
    """

    status = _runner_call_status_from_text(
        diagnostic.status,
        field_name="diagnostic.status",
    )
    return RunnerCallReconstructionDiagnostic(
        status=status,
        reason=_optional_runner_call_reason_from_text(
            diagnostic.reason,
            field_name="diagnostic.reason",
        ),
        missing_atom_kind=_optional_runner_call_missing_atom_kind_from_text(
            diagnostic.missing_atom_kind,
            field_name="diagnostic.missing_atom_kind",
        ),
        missing_ref_kind=_optional_runner_call_missing_ref_kind_from_text(
            diagnostic.missing_ref_kind,
            field_name="diagnostic.missing_ref_kind",
        ),
        missing_ref=diagnostic.missing_ref,
        observed_count=diagnostic.observed_count,
        expected_count=diagnostic.expected_count,
        observed_digest=diagnostic.observed_digest,
        expected_digest=diagnostic.expected_digest,
        consumer_boundary=(RunnerCallReconstructionConsumerBoundary.TOOL_TRACE_QUERY),
    )


def _summary_required_text(
    summary: Mapping[str, JsonValue], field_name: str
) -> str:
    """读取 summary 中的必填非空文本。

    :param summary: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = summary.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"tool trace summary field {field_name} must be text")


def _summary_optional_text(
    summary: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 summary 中的可选非空文本。

    :param summary: JSON object。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    value = summary.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"tool trace summary field {field_name} must be text")


def _summary_optional_int(
    summary: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """读取 summary 中的可选非负整数。

    :param summary: JSON object。
    :param field_name: 字段名。
    :returns: 整数或 ``None``。
    :raises HostDurableError: 字段存在但不是非负整数时抛出。
    """

    value = summary.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(
            f"tool trace summary field {field_name} must be non-negative integer"
        )
    return value


def _runner_call_status_from_text(
    value: str, *, field_name: str
) -> RunnerCallReconstructionStatus:
    """把必填文本转换为 runner-call reconstruction status。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: status enum 成员。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    try:
        return RunnerCallReconstructionStatus(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _runner_call_consumer_boundary_from_text(
    value: str, *, field_name: str
) -> RunnerCallReconstructionConsumerBoundary:
    """把必填文本转换为 runner-call reconstruction consumer boundary。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: consumer boundary enum 成员。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    try:
        return RunnerCallReconstructionConsumerBoundary(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _optional_runner_call_reason_from_text(
    value: str | None,
    *,
    field_name: str,
) -> RunnerCallReconstructionDiagnosticReason | None:
    """把可选文本转换为 runner-call reconstruction reason。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: reason enum 成员或 ``None``。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    if value is None:
        return None
    try:
        return RunnerCallReconstructionDiagnosticReason(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _optional_runner_call_missing_atom_kind_from_text(
    value: str | None,
    *,
    field_name: str,
) -> RunnerCallReconstructionMissingAtomKind | None:
    """把可选文本转换为 runner-call reconstruction missing atom kind。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: missing atom kind enum 成员或 ``None``。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    if value is None:
        return None
    try:
        return RunnerCallReconstructionMissingAtomKind(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _optional_runner_call_missing_ref_kind_from_text(
    value: str | None,
    *,
    field_name: str,
) -> RunnerCallReconstructionMissingRefKind | None:
    """把可选文本转换为 runner-call reconstruction missing ref kind。

    :param value: 待转换文本。
    :param field_name: 错误消息字段名。
    :returns: missing ref kind enum 成员或 ``None``。
    :raises HostDurableError: 值不在 enum 内时抛出。
    """

    if value is None:
        return None
    try:
        return RunnerCallReconstructionMissingRefKind(value)
    except ValueError as exc:
        raise HostDurableError(f"tool trace {field_name} is unsupported") from exc


def _validate_query_page_input(after_event_sequence: int, limit: int) -> None:
    """校验 Tool Trace 查询分页输入。

    :param after_event_sequence: EventLog cursor。
    :param limit: 返回行数上限。
    :returns: ``None``。
    :raises HostDurableError: cursor 或 limit 非法时抛出。
    """

    if after_event_sequence < _MIN_EVENT_CURSOR:
        raise HostDurableError("tool trace after_event_sequence is invalid")
    if limit < _MIN_QUERY_LIMIT or limit > TOOL_TRACE_QUERY_MAX_LIMIT:
        raise HostDurableError("tool trace query limit is invalid")


def _validate_hot_row(row: ToolTraceHotRow) -> None:
    """校验 Tool Trace hot row 写入输入。

    :param row: 待写入 hot row。
    :returns: ``None``。
    :raises HostDurableError: row 字段非法时抛出。
    """

    _require_non_empty_text(row.trace_id, field_name="trace_id")
    _require_non_empty_text(row.event_id, field_name="event_id")
    if row.event_sequence <= _MIN_EVENT_CURSOR:
        raise HostDurableError("tool trace event_sequence must be positive")
    _require_non_empty_text(row.event_type, field_name="event_type")
    _require_non_empty_text(row.event_class, field_name="event_class")
    _require_non_empty_text(row.session_id, field_name="session_id")
    _require_optional_non_empty_text(row.run_id, field_name="run_id")
    _require_optional_non_empty_text(row.attempt_id, field_name="attempt_id")
    _require_optional_non_empty_text(row.execution_id, field_name="execution_id")
    _require_optional_non_empty_text(row.tool_call_id, field_name="tool_call_id")
    _require_optional_non_empty_text(row.tool_name, field_name="tool_name")
    _require_optional_non_empty_text(
        row.provider_request_id, field_name="provider_request_id"
    )
    _require_optional_non_empty_text(row.diagnostic_ref, field_name="diagnostic_ref")
    _require_optional_non_empty_text(
        row.normalized_arguments_digest,
        field_name="normalized_arguments_digest",
    )
    _require_optional_non_empty_text(
        row.semantic_input_digest,
        field_name="semantic_input_digest",
    )
    _require_optional_non_empty_text(row.result_digest, field_name="result_digest")
    _require_optional_non_empty_text(row.payload_ref, field_name="payload_ref")
    _require_optional_non_empty_text(row.payload_digest, field_name="payload_digest")
    _require_optional_non_empty_text(
        row.policy_decision_json, field_name="policy_decision_json"
    )
    _require_optional_non_empty_text(row.cold_trace_ref, field_name="cold_trace_ref")
    _require_optional_non_empty_text(
        row.cold_trace_digest, field_name="cold_trace_digest"
    )
    _require_non_empty_text(row.projected_at, field_name="projected_at")
    _require_non_empty_text(row.updated_at, field_name="updated_at")
    canonical_json_dumps(row.trace_summary)


def _hot_row_from_host_row(row: HostRow) -> ToolTraceHotRow:
    """把通用 HostRow 转换为 ToolTraceHotRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: Tool Trace hot row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    return ToolTraceHotRow(
        trace_id=_require_text(row.get("trace_id"), field_name="trace_id"),
        event_id=_require_text(row.get("event_id"), field_name="event_id"),
        event_sequence=_require_int(
            row.get("event_sequence"), field_name="event_sequence"
        ),
        event_type=_require_text(row.get("event_type"), field_name="event_type"),
        event_class=_require_text(row.get("event_class"), field_name="event_class"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        run_id=_optional_text(row.get("run_id"), field_name="run_id"),
        attempt_id=_optional_text(row.get("attempt_id"), field_name="attempt_id"),
        execution_id=_optional_text(
            row.get("execution_id"), field_name="execution_id"
        ),
        tool_call_id=_optional_text(
            row.get("tool_call_id"), field_name="tool_call_id"
        ),
        tool_name=_optional_text(row.get("tool_name"), field_name="tool_name"),
        provider_request_id=_optional_text(
            row.get("provider_request_id"), field_name="provider_request_id"
        ),
        diagnostic_ref=_optional_text(
            row.get("diagnostic_ref"), field_name="diagnostic_ref"
        ),
        normalized_arguments_digest=_optional_text(
            row.get("normalized_arguments_digest"),
            field_name="normalized_arguments_digest",
        ),
        semantic_input_digest=_optional_text(
            row.get("semantic_input_digest"),
            field_name="semantic_input_digest",
        ),
        result_digest=_optional_text(
            row.get("result_digest"), field_name="result_digest"
        ),
        payload_ref=_optional_text(row.get("payload_ref"), field_name="payload_ref"),
        payload_digest=_optional_text(
            row.get("payload_digest"), field_name="payload_digest"
        ),
        policy_decision_json=_optional_text(
            row.get("policy_decision_json"), field_name="policy_decision_json"
        ),
        trace_summary=_json_object_from_text(
            _require_text(row.get("trace_summary_json"), field_name="trace_summary_json")
        ),
        cold_trace_ref=_optional_text(
            row.get("cold_trace_ref"), field_name="cold_trace_ref"
        ),
        cold_trace_digest=_optional_text(
            row.get("cold_trace_digest"), field_name="cold_trace_digest"
        ),
        projected_at=_require_text(row.get("projected_at"), field_name="projected_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
    )


def _json_object_from_text(value: str) -> Mapping[str, JsonValue]:
    """解析 durable JSON object 文本。

    :param value: JSON object 文本。
    :returns: JSON object。
    :raises HostDurableError: JSON 非法或不是 object 时抛出。
    """

    try:
        parsed = cast(JsonValue, json.loads(value))
    except json.JSONDecodeError as exc:
        raise HostDurableError("tool trace summary JSON is invalid") from exc
    if not isinstance(parsed, Mapping):
        raise HostDurableError("tool trace summary JSON must be object")
    return cast(Mapping[str, JsonValue], parsed)


__all__ = [
    "TOOL_TRACE_QUERY_MAX_LIMIT",
    "CompactorResponseDisposition",
    "ProjectorMetadataSummary",
    "RunnerCallReconstructionConsumerBoundary",
    "RunnerCallReconstructionDiagnostic",
    "RunnerCallReconstructionDiagnosticReason",
    "RunnerCallReconstructionMissingAtomKind",
    "RunnerCallReconstructionMissingRefKind",
    "RunnerCallReconstructionSignal",
    "RunnerCallReconstructionSignalPage",
    "RunnerCallReconstructionStatus",
    "RunnerCallResolvedProjection",
    "ResolvedCompactorResponseIdentity",
    "ToolTraceHotRow",
    "ToolTraceHotRowWriteResult",
    "ToolTraceHotRowWriteStatus",
    "ToolTraceQueryPage",
    "ToolTraceResolvedJsonPayload",
    "ToolTraceResolvedRowPayloads",
    "find_tool_trace_by_diagnostic_ref",
    "find_tool_trace_by_provider_request_id",
    "find_tool_trace_by_tool_call_id",
    "insert_tool_trace_hot_row_if_absent",
    "read_runner_call_reconstruction_signals_by_run",
    "read_tool_trace_json_payload",
    "read_tool_trace_by_run",
    "read_tool_trace_hot_row",
    "read_tool_trace_page",
    "resolve_runner_call_projection_from_signal",
    "resolve_tool_trace_hot_row_payloads",
]
