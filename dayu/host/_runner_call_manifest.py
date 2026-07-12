"""Host runner-call manifest 与固定 hot payload 的共享契约 owner。

本模块统一产生和解析 ``RUNNER_CALL_INPUT_ASSEMBLED`` hot payload，并解析
完整 durable manifest 语义图。ordinary、Engine continuation 与 compactor
producer 只提供严格 typed atoms；Tool Trace 与 Engine ingest 也必须通过本
owner 消费，逐消息内容与 projector metadata 始终留在 durable descriptor 中。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.engine_events import (
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    runner_role_sequence_digest,
)
from dayu.host.durable.codec import is_sha256_digest, sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION

_RUNNER_CALL_HOT_FIELDS = frozenset(
    {
        "session_id",
        "host_run_id",
        "attempt_id",
        "execution_id",
        "runner_call_index",
        "runner_call_kind",
        "runner_call_trigger_reason",
        "iteration_id",
        "iteration_index",
        "manifest_payload_ref",
        "manifest_digest",
        "manifest_schema_version",
        "validation_status",
        "message_count",
        "role_sequence_digest",
        "input_projection_digest",
        "runner_call_projection_artifact_ref",
        "runner_call_projection_artifact_digest",
        "runner_call_projection_artifact_size_bytes",
        "diagnostic",
    }
)
_RUNNER_CALL_DIAGNOSTIC_FIELDS = frozenset(
    {
        "status",
        "reason",
        "missing_atom_kind",
        "missing_ref_kind",
        "missing_ref",
        "observed_count",
        "expected_count",
        "observed_digest",
        "expected_digest",
        "consumer_boundary",
    }
)
_RUNNER_CALL_MANIFEST_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_id",
        "session_id",
        "host_run_id",
        "attempt_id",
        "execution_id",
        "runner_call_index",
        "runner_call_kind",
        "runner_call_trigger_reason",
        "iteration_id",
        "iteration_index",
        "message_count",
        "role_sequence_digest",
        "runner_input_serializer_schema_version",
        "input_projection_digest",
        "message_entries",
        "source_cursor_refs",
        "tool_schema_snapshot_refs",
        "memory_snapshot_cursor_ref",
        "compact_artifact_refs",
        "context_fallback_decision_ref",
        "projector_metadata",
        "compactor_identity",
        "diagnostic",
    }
)
_RUNNER_CALL_MANIFEST_PROJECTION_FIELDS = frozenset(
    {
        "runner_call_projection_artifact_ref",
        "runner_call_projection_artifact_digest",
        "runner_call_projection_artifact_size_bytes",
    }
)
_RUNNER_CALL_MESSAGE_FIELDS = frozenset(
    {
        "index",
        "role",
        "content_digest",
        "content_size_bytes",
        "source_refs",
        "projection_artifact_ref",
        "projection_artifact_digest",
        "projector_metadata_id",
        "provider_tool_calls_digest",
        "reasoning_content_digest",
    }
)
_RUNNER_CALL_PROJECTOR_METADATA_FIELDS = frozenset(
    {
        "projector_metadata_id",
        "projector_id",
        "projector_schema_version",
        "projector_digest",
        "purpose",
        "source_contract_refs",
    }
)
_COMPACTOR_IDENTITY_FIELDS = frozenset(
    {
        "parent_host_run_id",
        "parent_session_id",
        "compaction_operation_id",
        "compactor_engine_run_id",
        "compaction_attempt_number",
        "compaction_request_digest",
        "compactor_input_projection_ref",
    }
)
_RUNNER_CALL_VALIDATION_STATUSES = frozenset(
    {"complete", "limited_signal", "mismatch"}
)
_RUNNER_CALL_KINDS = frozenset(
    {
        "initial_user_dispatch",
        "followup_user_dispatch",
        "tool_result_continuation",
        "post_compaction_dispatch",
        "compactor_proposal",
    }
)
_RUNNER_CALL_TRIGGER_REASONS = frozenset(
    {
        "initial_user_input",
        "followup_user_input",
        "tool_results_available",
        "force_answer_after_tool_limit",
        "finish_reason_length_continuation",
        "host_retry",
        "host_replay",
        "host_resume",
        "context_compaction_completed",
        "context_compaction_initial_proposal",
        "context_compaction_repair_attempt",
        "context_compaction_retry_attempt",
    }
)
_RUNNER_CALL_MESSAGE_ROLES = frozenset({"system", "user", "assistant", "tool"})
_RUNNER_CALL_PROJECTOR_IDS = frozenset(
    {
        "run_input_system_context",
        "user_input_message",
        "assistant_history_message",
        "tool_result_message",
        "compact_memory_material",
        "recent_window_material",
        "guidance_message",
        "tool_schema_snapshot",
        "compactor_system_prompt",
        "compactor_user_prompt",
        "engine_observed_runner_input_signal",
    }
)
_RUNNER_CALL_PROJECTOR_PURPOSES = frozenset(
    {
        "ordinary_run_input",
        "tool_continuation_input",
        "post_compaction_input",
        "compactor_proposal_input",
        "retry_replay_resume_input",
        "forced_answer_input",
        "length_continuation_input",
    }
)
_RUNNER_CALL_DIAGNOSTIC_REASONS = frozenset(
    {
        "missing_runner_call_manifest",
        "missing_projection_artifact",
        "missing_tool_call_arguments_atom",
        "missing_semantic_query_atom",
        "missing_compactor_manifest",
        "missing_memory_snapshot_body",
        "unsupported_projector_version",
        "message_count_mismatch",
        "role_sequence_digest_mismatch",
        "input_projection_digest_mismatch",
        "payload_digest_mismatch",
        "unresolvable_ref",
        "provider_specific_atom_deferred",
    }
)
_RUNNER_CALL_MISSING_ATOM_KINDS = frozenset(
    {
        "tool_call_arguments",
        "semantic_query",
        "runner_call_manifest",
        "compactor_manifest",
        "projection_artifact",
        "memory_snapshot_body",
    }
)
_RUNNER_CALL_MISSING_REF_KINDS = frozenset(
    {"payload_ref", "artifact_ref", "event_ref", "cursor_ref"}
)


@dataclass(frozen=True, slots=True)
class RunnerCallHotDiagnostic:
    """runner-call hot payload 的固定 shape 诊断 atoms。

    :param status: reconstruction validation 状态。
    :param reason: 非 complete 状态的封闭原因。
    :param missing_atom_kind: 可选缺失 atom kind。
    :param missing_ref_kind: 可选缺失 ref kind。
    :param missing_ref: 可选缺失引用标签。
    :param observed_count: 可选观察数量。
    :param expected_count: 可选期望数量。
    :param observed_digest: 可选观察 digest。
    :param expected_digest: 可选期望 digest。
    :param consumer_boundary: 产生诊断的 Host 边界。
    """

    status: str
    reason: str | None
    missing_atom_kind: str | None
    missing_ref_kind: str | None
    missing_ref: str | None
    observed_count: int | None
    expected_count: int | None
    observed_digest: str | None
    expected_digest: str | None
    consumer_boundary: str


@dataclass(frozen=True, slots=True)
class RunnerCallHotAtoms:
    """runner-call canonical event 的固定上界 hot atoms。

    :param session_id: Session id。
    :param host_run_id: Host Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param runner_call_index: Run 内 runner-call 顺序。
    :param runner_call_kind: runner-call 业务 kind。
    :param runner_call_trigger_reason: runner-call 触发原因。
    :param iteration_id: 可选 Engine iteration id。
    :param iteration_index: 可选 Engine iteration 顺序。
    :param manifest_payload_ref: 完整 manifest descriptor ref。
    :param manifest_digest: 完整 manifest canonical digest。
    :param manifest_schema_version: manifest schema version。
    :param validation_status: reconstruction validation 状态。
    :param message_count: 实际 runner message 数。
    :param role_sequence_digest: message role 序列 digest。
    :param input_projection_digest: 输入投影 digest。
    :param runner_call_projection_artifact_ref: 可选完整输入投影 descriptor ref。
    :param runner_call_projection_artifact_digest: 可选完整输入投影 digest。
    :param runner_call_projection_artifact_size_bytes: 可选完整输入投影字节数。
    :param diagnostic: 固定 shape reconstruction 诊断。
    """

    session_id: str
    host_run_id: str
    attempt_id: str | None
    execution_id: str | None
    runner_call_index: int
    runner_call_kind: str
    runner_call_trigger_reason: str
    iteration_id: str | None
    iteration_index: int | None
    manifest_payload_ref: str
    manifest_digest: str
    manifest_schema_version: str
    validation_status: str
    message_count: int
    role_sequence_digest: str
    input_projection_digest: str
    runner_call_projection_artifact_ref: str | None
    runner_call_projection_artifact_digest: str | None
    runner_call_projection_artifact_size_bytes: int | None
    diagnostic: RunnerCallHotDiagnostic


@dataclass(frozen=True, slots=True)
class RunnerCallProjectorMetadata:
    """runner-call manifest 的完整 projector metadata descriptor。

    :param projector_metadata_id: manifest 内 projector metadata 唯一 id。
    :param projector_id: projector 语义 id。
    :param projector_schema_version: projector schema version。
    :param projector_digest: projector 输入或投影语义 digest。
    :param purpose: projector 的业务目的。
    :param source_contract_refs: projector 依赖的 durable contract refs。
    """

    projector_metadata_id: str
    projector_id: str
    projector_schema_version: str
    projector_digest: str
    purpose: str
    source_contract_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunnerCallManifestIdentity:
    """runner-call manifest 的稳定 identity。

    :param schema_version: manifest schema version。
    :param manifest_id: manifest logical id。
    :param session_id: Session id。
    :param host_run_id: Host Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param runner_call_index: runner-call 顺序。
    :param runner_call_kind: runner-call 业务 kind。
    :param runner_call_trigger_reason: runner-call 触发原因。
    :param iteration_id: 可选 Engine iteration id。
    :param iteration_index: 可选 Engine iteration 顺序。
    """

    schema_version: str
    manifest_id: str
    session_id: str
    host_run_id: str
    attempt_id: str | None
    execution_id: str | None
    runner_call_index: int
    runner_call_kind: str
    runner_call_trigger_reason: str
    iteration_id: str | None
    iteration_index: int | None


@dataclass(frozen=True, slots=True)
class RunnerCallProjectionDescriptor:
    """runner-call rendered input projection descriptor 摘要。

    :param payload_ref: projection payload ref。
    :param payload_digest: projection payload digest。
    :param payload_size_bytes: projection payload 字节数。
    """

    payload_ref: str
    payload_digest: str
    payload_size_bytes: int


@dataclass(frozen=True, slots=True)
class RunnerCallMessageEntry:
    """runner-call manifest 的单条 message provenance。

    :param index: message 连续顺序。
    :param role: runner message role。
    :param content_digest: rendered content digest。
    :param content_size_bytes: rendered content 字节数。
    :param source_refs: message source refs。
    :param projection_artifact_ref: 可选 projection ref。
    :param projection_artifact_digest: 可选 projection digest。
    :param projector_metadata_id: 所引用 metadata id。
    :param provider_tool_calls_digest: 可选 provider tool-calls digest。
    :param reasoning_content_digest: 可选 reasoning digest。
    """

    index: int
    role: str
    content_digest: str
    content_size_bytes: int
    source_refs: tuple[str, ...]
    projection_artifact_ref: str | None
    projection_artifact_digest: str | None
    projector_metadata_id: str
    provider_tool_calls_digest: str | None
    reasoning_content_digest: str | None


@dataclass(frozen=True, slots=True)
class RunnerCallManifestSourceRefs:
    """runner-call manifest 的 source/ref 集合。

    :param source_cursor_refs: source cursor refs。
    :param tool_schema_snapshot_refs: tool schema snapshot refs。
    :param memory_snapshot_cursor_ref: 可选 memory cursor ref。
    :param compact_artifact_refs: compact artifact refs。
    :param context_fallback_decision_ref: 可选 fallback decision ref。
    """

    source_cursor_refs: tuple[str, ...]
    tool_schema_snapshot_refs: tuple[str, ...]
    memory_snapshot_cursor_ref: str | None
    compact_artifact_refs: tuple[str, ...]
    context_fallback_decision_ref: str | None


@dataclass(frozen=True, slots=True)
class RunnerCallCompactorIdentity:
    """compactor proposal runner-call 的 typed identity。

    :param parent_host_run_id: parent Host Run id。
    :param parent_session_id: parent Session id。
    :param compaction_operation_id: compaction operation id。
    :param compactor_engine_run_id: compactor Engine run id。
    :param compaction_attempt_number: proposal attempt 序号。
    :param compaction_request_digest: compaction request digest。
    :param compactor_input_projection_ref: compactor input projection ref。
    """

    parent_host_run_id: str
    parent_session_id: str
    compaction_operation_id: str
    compactor_engine_run_id: str
    compaction_attempt_number: int
    compaction_request_digest: str
    compactor_input_projection_ref: str


@dataclass(frozen=True, slots=True)
class RunnerCallInputManifest:
    """完成完整语义图校验的 runner-call manifest。

    :param identity: manifest identity。
    :param validation_status: complete / limited_signal / mismatch。
    :param message_count: runner message 数。
    :param role_sequence_digest: message role 序列 digest。
    :param input_projection_digest: input projection digest。
    :param projection_descriptor: 可选 rendered input projection descriptor。
    :param message_entries: typed message entries。
    :param source_refs: typed source/ref 集合。
    :param projector_metadata: typed projector metadata。
    :param compactor_identity: 可选 compactor identity。
    :param diagnostic: 非 complete manifest diagnostic；complete 时为 ``None``。
    """

    identity: RunnerCallManifestIdentity
    validation_status: str
    message_count: int
    role_sequence_digest: str
    input_projection_digest: str
    projection_descriptor: RunnerCallProjectionDescriptor | None
    message_entries: tuple[RunnerCallMessageEntry, ...]
    source_refs: RunnerCallManifestSourceRefs
    projector_metadata: tuple[RunnerCallProjectorMetadata, ...]
    compactor_identity: RunnerCallCompactorIdentity | None
    diagnostic: RunnerCallHotDiagnostic | None


def complete_runner_call_hot_diagnostic(
    *,
    status: str,
    message_count: int,
    role_sequence_digest: str,
    consumer_boundary: str,
) -> RunnerCallHotDiagnostic:
    """构造 complete runner-call 的固定诊断 atoms。

    :param status: complete validation 状态文本。
    :param message_count: 实际与期望 message 数。
    :param role_sequence_digest: 实际与期望 role digest。
    :param consumer_boundary: producer 边界。
    :returns: complete diagnostic atoms。
    :raises HostDurableError: 状态、数量、digest 或边界非法时抛出。
    """

    diagnostic = RunnerCallHotDiagnostic(
        status=status,
        reason=None,
        missing_atom_kind=None,
        missing_ref_kind=None,
        missing_ref=None,
        observed_count=message_count,
        expected_count=message_count,
        observed_digest=role_sequence_digest,
        expected_digest=role_sequence_digest,
        consumer_boundary=consumer_boundary,
    )
    _validate_diagnostic(diagnostic)
    return diagnostic


def runner_call_hot_diagnostic_from_json(
    value: Mapping[str, JsonValue],
) -> RunnerCallHotDiagnostic:
    """把 manifest 内固定诊断 JSON 还原为 typed hot atoms。

    :param value: manifest diagnostic JSON object。
    :returns: typed diagnostic atoms。
    :raises HostDurableError: 字段缺失、类型非法或 digest 非法时抛出。
    """

    _require_exact_fields(
        value,
        expected_fields=_RUNNER_CALL_DIAGNOSTIC_FIELDS,
        field_name="runner-call diagnostic",
    )
    diagnostic = RunnerCallHotDiagnostic(
        status=_required_text(value, "status"),
        reason=_optional_text(value, "reason"),
        missing_atom_kind=_optional_text(value, "missing_atom_kind"),
        missing_ref_kind=_optional_text(value, "missing_ref_kind"),
        missing_ref=_optional_text(value, "missing_ref"),
        observed_count=_optional_non_negative_int(value, "observed_count"),
        expected_count=_optional_non_negative_int(value, "expected_count"),
        observed_digest=_optional_digest(value, "observed_digest"),
        expected_digest=_optional_digest(value, "expected_digest"),
        consumer_boundary=_required_text(value, "consumer_boundary"),
    )
    _validate_diagnostic(diagnostic)
    return diagnostic


def runner_call_hot_payload(
    atoms: RunnerCallHotAtoms,
    *,
    manifest: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """从 typed atoms 与完整 manifest 构造唯一 hot payload shape。

    :param atoms: producer 提供的固定上界 atoms。
    :param manifest: 同源完整 runner-call manifest body。
    :returns: 不含逐消息数组的 EventLog hot payload。
    :raises HostDurableError: hot/manifest 任一 contract 或同源校验失败时抛出。
    """

    _validate_hot_atoms(atoms)
    parse_runner_call_manifest(manifest, hot_payload=atoms)
    diagnostic = atoms.diagnostic
    return {
        "session_id": atoms.session_id,
        "host_run_id": atoms.host_run_id,
        "attempt_id": atoms.attempt_id,
        "execution_id": atoms.execution_id,
        "runner_call_index": atoms.runner_call_index,
        "runner_call_kind": atoms.runner_call_kind,
        "runner_call_trigger_reason": atoms.runner_call_trigger_reason,
        "iteration_id": atoms.iteration_id,
        "iteration_index": atoms.iteration_index,
        "manifest_payload_ref": atoms.manifest_payload_ref,
        "manifest_digest": atoms.manifest_digest,
        "manifest_schema_version": atoms.manifest_schema_version,
        "validation_status": atoms.validation_status,
        "message_count": atoms.message_count,
        "role_sequence_digest": atoms.role_sequence_digest,
        "input_projection_digest": atoms.input_projection_digest,
        "runner_call_projection_artifact_ref": (
            atoms.runner_call_projection_artifact_ref
        ),
        "runner_call_projection_artifact_digest": (
            atoms.runner_call_projection_artifact_digest
        ),
        "runner_call_projection_artifact_size_bytes": (
            atoms.runner_call_projection_artifact_size_bytes
        ),
        "diagnostic": {
            "status": diagnostic.status,
            "reason": diagnostic.reason,
            "missing_atom_kind": diagnostic.missing_atom_kind,
            "missing_ref_kind": diagnostic.missing_ref_kind,
            "missing_ref": diagnostic.missing_ref,
            "observed_count": diagnostic.observed_count,
            "expected_count": diagnostic.expected_count,
            "observed_digest": diagnostic.observed_digest,
            "expected_digest": diagnostic.expected_digest,
            "consumer_boundary": diagnostic.consumer_boundary,
        },
    }


def parse_runner_call_hot_payload(
    value: Mapping[str, JsonValue],
) -> RunnerCallHotAtoms:
    """解析并校验 ``RUNNER_CALL_INPUT_ASSEMBLED`` hot payload。

    本函数同时拒绝旧 ``projector_metadata_summary`` 数组、缺失 diagnostic
    与任意未知字段，不提供旧 hot row 兼容读取。

    :param value: source EventLog hot payload JSON object。
    :returns: 完整校验后的 typed hot atoms。
    :raises HostDurableError: 字段集、字段类型或跨字段不变量非法时抛出。
    """

    _require_exact_fields(
        value,
        expected_fields=_RUNNER_CALL_HOT_FIELDS,
        field_name="runner-call hot payload",
    )
    diagnostic_value = value.get("diagnostic")
    if not isinstance(diagnostic_value, Mapping):
        raise HostDurableError("runner-call hot diagnostic must be object")
    diagnostic = runner_call_hot_diagnostic_from_json(
        cast(Mapping[str, JsonValue], diagnostic_value)
    )
    atoms = RunnerCallHotAtoms(
        session_id=_required_text(value, "session_id"),
        host_run_id=_required_text(value, "host_run_id"),
        attempt_id=_optional_text(value, "attempt_id"),
        execution_id=_optional_text(value, "execution_id"),
        runner_call_index=_required_non_negative_int(value, "runner_call_index"),
        runner_call_kind=_required_text(value, "runner_call_kind"),
        runner_call_trigger_reason=_required_text(
            value,
            "runner_call_trigger_reason",
        ),
        iteration_id=_optional_text(value, "iteration_id"),
        iteration_index=_optional_non_negative_int(value, "iteration_index"),
        manifest_payload_ref=_required_text(value, "manifest_payload_ref"),
        manifest_digest=_required_digest(value, "manifest_digest"),
        manifest_schema_version=_required_text(
            value,
            "manifest_schema_version",
        ),
        validation_status=_required_text(value, "validation_status"),
        message_count=_required_non_negative_int(value, "message_count"),
        role_sequence_digest=_required_digest(value, "role_sequence_digest"),
        input_projection_digest=_required_digest(
            value,
            "input_projection_digest",
        ),
        runner_call_projection_artifact_ref=_optional_text(
            value,
            "runner_call_projection_artifact_ref",
        ),
        runner_call_projection_artifact_digest=_optional_digest(
            value,
            "runner_call_projection_artifact_digest",
        ),
        runner_call_projection_artifact_size_bytes=_optional_non_negative_int(
            value,
            "runner_call_projection_artifact_size_bytes",
        ),
        diagnostic=diagnostic,
    )
    _validate_hot_atoms(atoms)
    return atoms


def runner_call_projector_metadata_descriptor(
    metadata: RunnerCallProjectorMetadata,
) -> Mapping[str, JsonValue]:
    """构造 runner-call manifest 的唯一六字段 projector metadata shape。

    :param metadata: producer 提供的完整 projector metadata。
    :returns: 只含六个契约字段的 durable manifest descriptor。
    :raises HostDurableError: id、schema、digest、purpose 或 source refs 非法时抛出。
    """

    for field_name, value in (
        ("projector_metadata_id", metadata.projector_metadata_id),
        ("projector_id", metadata.projector_id),
        ("projector_schema_version", metadata.projector_schema_version),
        ("purpose", metadata.purpose),
    ):
        _require_non_empty_text(value, field_name=field_name)
    _require_closed_text(
        metadata.projector_id,
        allowed_values=_RUNNER_CALL_PROJECTOR_IDS,
        field_name="projector_id",
    )
    _require_closed_text(
        metadata.purpose,
        allowed_values=_RUNNER_CALL_PROJECTOR_PURPOSES,
        field_name="purpose",
    )
    _require_digest(metadata.projector_digest, field_name="projector_digest")
    if not metadata.source_contract_refs:
        raise HostDurableError("source_contract_refs must not be empty")
    for source_contract_ref in metadata.source_contract_refs:
        _require_non_empty_text(
            source_contract_ref,
            field_name="source_contract_refs item",
        )
    return {
        "projector_metadata_id": metadata.projector_metadata_id,
        "projector_id": metadata.projector_id,
        "projector_schema_version": metadata.projector_schema_version,
        "projector_digest": metadata.projector_digest,
        "purpose": metadata.purpose,
        "source_contract_refs": list(metadata.source_contract_refs),
    }


def parse_runner_call_manifest(
    value: Mapping[str, JsonValue],
    *,
    hot_payload: RunnerCallHotAtoms,
) -> RunnerCallInputManifest:
    """解析完整 runner-call manifest 并校验 hot/manifest 同源关系。

    :param value: 已通过 durable bytes integrity 校验的 manifest JSON object。
    :param hot_payload: 已通过 hot contract 校验的同一 canonical event atoms。
    :returns: 完整语义图校验后的 typed manifest。
    :raises HostDurableError: schema、identity、message graph、metadata graph、
        projection pair、digest 或 hot/manifest identity 任一非法时抛出。
    """

    _validate_manifest_fields(value)
    identity = _parse_manifest_identity(value)
    message_count = _required_non_negative_int(value, "message_count")
    role_sequence_digest = _required_digest(value, "role_sequence_digest")
    serializer_schema_version = _required_text(
        value,
        "runner_input_serializer_schema_version",
    )
    if serializer_schema_version != RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION:
        raise HostDurableError(
            "runner-call manifest serializer schema version is unsupported"
        )
    input_projection_digest = _required_digest(
        value,
        "input_projection_digest",
    )
    projection_descriptor = _parse_manifest_projection_descriptor(value)
    message_entries = _parse_manifest_message_entries(value)
    projector_metadata = _parse_manifest_projector_metadata(value)
    source_refs = _parse_manifest_source_refs(value)
    validation_status, diagnostic = _parse_manifest_diagnostic(value)
    compactor_identity = _parse_compactor_identity(value)
    manifest = RunnerCallInputManifest(
        identity=identity,
        validation_status=validation_status,
        message_count=message_count,
        role_sequence_digest=role_sequence_digest,
        input_projection_digest=input_projection_digest,
        projection_descriptor=projection_descriptor,
        message_entries=message_entries,
        source_refs=source_refs,
        projector_metadata=projector_metadata,
        compactor_identity=compactor_identity,
        diagnostic=diagnostic,
    )
    _validate_manifest_graph(manifest)
    _validate_manifest_hot_identity(
        manifest,
        hot_payload=hot_payload,
        actual_manifest_digest=sha256_digest_json(value),
    )
    return manifest


def _validate_manifest_fields(value: Mapping[str, JsonValue]) -> None:
    """校验 manifest 顶层 required / optional 字段集合。

    :param value: manifest JSON object。
    :returns: ``None``。
    :raises HostDurableError: required 字段缺失或未知字段出现时抛出。
    """

    fields = frozenset(value)
    missing_fields = _RUNNER_CALL_MANIFEST_REQUIRED_FIELDS - fields
    if missing_fields:
        raise HostDurableError(
            "runner-call manifest required fields are missing: "
            + ",".join(sorted(missing_fields))
        )
    unknown_fields = fields - (
        _RUNNER_CALL_MANIFEST_REQUIRED_FIELDS
        | _RUNNER_CALL_MANIFEST_PROJECTION_FIELDS
    )
    if unknown_fields:
        raise HostDurableError(
            "runner-call manifest fields are unsupported: "
            + ",".join(sorted(unknown_fields))
        )
    projection_field_count = len(
        fields & _RUNNER_CALL_MANIFEST_PROJECTION_FIELDS
    )
    if projection_field_count not in (
        0,
        len(_RUNNER_CALL_MANIFEST_PROJECTION_FIELDS),
    ):
        raise HostDurableError(
            "runner-call manifest projection descriptor fields must appear together"
        )


def _parse_manifest_identity(
    value: Mapping[str, JsonValue],
) -> RunnerCallManifestIdentity:
    """解析并校验 manifest identity。

    :param value: manifest JSON object。
    :returns: typed manifest identity。
    :raises HostDurableError: schema、identity 类型或 closed enum 非法时抛出。
    """

    schema_version = _required_text(value, "schema_version")
    if schema_version != RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION:
        raise HostDurableError("runner-call manifest schema version is unsupported")
    runner_call_kind = _required_text(value, "runner_call_kind")
    _require_closed_text(
        runner_call_kind,
        allowed_values=_RUNNER_CALL_KINDS,
        field_name="runner_call_kind",
    )
    runner_call_trigger_reason = _required_text(
        value,
        "runner_call_trigger_reason",
    )
    _require_closed_text(
        runner_call_trigger_reason,
        allowed_values=_RUNNER_CALL_TRIGGER_REASONS,
        field_name="runner_call_trigger_reason",
    )
    attempt_id = _optional_text(value, "attempt_id")
    execution_id = _optional_text(value, "execution_id")
    if (attempt_id is None) != (execution_id is None):
        raise HostDurableError(
            "runner-call manifest attempt_id/execution_id must pair"
        )
    iteration_id = _optional_text(value, "iteration_id")
    iteration_index = _optional_non_negative_int(value, "iteration_index")
    if (iteration_id is None) != (iteration_index is None):
        raise HostDurableError(
            "runner-call manifest iteration_id/iteration_index must pair"
        )
    return RunnerCallManifestIdentity(
        schema_version=schema_version,
        manifest_id=_required_text(value, "manifest_id"),
        session_id=_required_text(value, "session_id"),
        host_run_id=_required_text(value, "host_run_id"),
        attempt_id=attempt_id,
        execution_id=execution_id,
        runner_call_index=_required_non_negative_int(
            value,
            "runner_call_index",
        ),
        runner_call_kind=runner_call_kind,
        runner_call_trigger_reason=runner_call_trigger_reason,
        iteration_id=iteration_id,
        iteration_index=iteration_index,
    )


def _parse_manifest_projection_descriptor(
    value: Mapping[str, JsonValue],
) -> RunnerCallProjectionDescriptor | None:
    """解析 manifest-level projection descriptor 三元组。

    :param value: manifest JSON object。
    :returns: 完整 descriptor；三字段整体缺失或整体为 ``null`` 时返回
        ``None``。
    :raises HostDurableError: 字段只出现一部分或值只提供一部分时抛出。
    """

    if not _RUNNER_CALL_MANIFEST_PROJECTION_FIELDS.issubset(value):
        return None
    payload_ref = _optional_text(
        value,
        "runner_call_projection_artifact_ref",
    )
    payload_digest = _optional_digest(
        value,
        "runner_call_projection_artifact_digest",
    )
    payload_size_bytes = _optional_non_negative_int(
        value,
        "runner_call_projection_artifact_size_bytes",
    )
    fields = (payload_ref, payload_digest, payload_size_bytes)
    if all(field is None for field in fields):
        return None
    if any(field is None for field in fields):
        raise HostDurableError(
            "runner-call manifest projection descriptor ref/digest/size must pair"
        )
    if payload_ref is None or payload_digest is None or payload_size_bytes is None:
        raise HostDurableError("runner-call manifest projection descriptor is invalid")
    return RunnerCallProjectionDescriptor(
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        payload_size_bytes=payload_size_bytes,
    )


def _parse_manifest_message_entries(
    value: Mapping[str, JsonValue],
) -> tuple[RunnerCallMessageEntry, ...]:
    """解析 manifest message entry 数组。

    :param value: manifest JSON object。
    :returns: typed message entries。
    :raises HostDurableError: 数组、字段集、role、digest 或 projection pair
        非法时抛出。
    """

    raw_entries = _required_array(value, "message_entries")
    entries: list[RunnerCallMessageEntry] = []
    for raw_entry in raw_entries:
        entry = _required_object(raw_entry, field_name="message_entries item")
        _require_exact_fields(
            entry,
            expected_fields=_RUNNER_CALL_MESSAGE_FIELDS,
            field_name="runner-call message entry",
        )
        role = _required_text(entry, "role")
        _require_closed_text(
            role,
            allowed_values=_RUNNER_CALL_MESSAGE_ROLES,
            field_name="message entry role",
        )
        projection_ref = _optional_text(entry, "projection_artifact_ref")
        projection_digest = _optional_digest(
            entry,
            "projection_artifact_digest",
        )
        if (projection_ref is None) != (projection_digest is None):
            raise HostDurableError(
                "runner-call message projection ref/digest must pair"
            )
        entries.append(
            RunnerCallMessageEntry(
                index=_required_non_negative_int(entry, "index"),
                role=role,
                content_digest=_required_digest(entry, "content_digest"),
                content_size_bytes=_required_non_negative_int(
                    entry,
                    "content_size_bytes",
                ),
                source_refs=_text_tuple(
                    entry,
                    "source_refs",
                    allow_empty=True,
                ),
                projection_artifact_ref=projection_ref,
                projection_artifact_digest=projection_digest,
                projector_metadata_id=_required_text(
                    entry,
                    "projector_metadata_id",
                ),
                provider_tool_calls_digest=_optional_digest(
                    entry,
                    "provider_tool_calls_digest",
                ),
                reasoning_content_digest=_optional_digest(
                    entry,
                    "reasoning_content_digest",
                ),
            )
        )
    return tuple(entries)


def _parse_manifest_projector_metadata(
    value: Mapping[str, JsonValue],
) -> tuple[RunnerCallProjectorMetadata, ...]:
    """解析 manifest projector metadata 数组。

    :param value: manifest JSON object。
    :returns: typed projector metadata。
    :raises HostDurableError: 六字段 contract、closed enum、digest 或 id 唯一性
        非法时抛出。
    """

    raw_items = _required_array(value, "projector_metadata")
    items: list[RunnerCallProjectorMetadata] = []
    metadata_ids: set[str] = set()
    for raw_item in raw_items:
        item = _required_object(
            raw_item,
            field_name="projector_metadata item",
        )
        _require_exact_fields(
            item,
            expected_fields=_RUNNER_CALL_PROJECTOR_METADATA_FIELDS,
            field_name="runner-call projector metadata",
        )
        metadata = RunnerCallProjectorMetadata(
            projector_metadata_id=_required_text(
                item,
                "projector_metadata_id",
            ),
            projector_id=_required_text(item, "projector_id"),
            projector_schema_version=_required_text(
                item,
                "projector_schema_version",
            ),
            projector_digest=_required_digest(item, "projector_digest"),
            purpose=_required_text(item, "purpose"),
            source_contract_refs=_text_tuple(
                item,
                "source_contract_refs",
                allow_empty=False,
            ),
        )
        _require_closed_text(
            metadata.projector_id,
            allowed_values=_RUNNER_CALL_PROJECTOR_IDS,
            field_name="projector_id",
        )
        _require_closed_text(
            metadata.purpose,
            allowed_values=_RUNNER_CALL_PROJECTOR_PURPOSES,
            field_name="purpose",
        )
        if metadata.projector_metadata_id in metadata_ids:
            raise HostDurableError(
                "runner-call manifest projector_metadata_id must be unique"
            )
        metadata_ids.add(metadata.projector_metadata_id)
        items.append(metadata)
    return tuple(items)


def _parse_manifest_source_refs(
    value: Mapping[str, JsonValue],
) -> RunnerCallManifestSourceRefs:
    """解析 manifest source/ref 字段。

    :param value: manifest JSON object。
    :returns: typed source/ref 集合。
    :raises HostDurableError: ref 数组或可选 ref 类型非法时抛出。
    """

    return RunnerCallManifestSourceRefs(
        source_cursor_refs=_text_tuple(
            value,
            "source_cursor_refs",
            allow_empty=True,
        ),
        tool_schema_snapshot_refs=_text_tuple(
            value,
            "tool_schema_snapshot_refs",
            allow_empty=True,
        ),
        memory_snapshot_cursor_ref=_optional_text(
            value,
            "memory_snapshot_cursor_ref",
        ),
        compact_artifact_refs=_text_tuple(
            value,
            "compact_artifact_refs",
            allow_empty=True,
        ),
        context_fallback_decision_ref=_optional_text(
            value,
            "context_fallback_decision_ref",
        ),
    )


def _parse_manifest_diagnostic(
    value: Mapping[str, JsonValue],
) -> tuple[str, RunnerCallHotDiagnostic | None]:
    """解析 manifest validation status 与 optional diagnostic。

    complete manifest 继续使用 ``diagnostic=null``；显式 complete diagnostic
    只属于 hot payload。非 complete manifest 必须携带完整 typed diagnostic。

    :param value: manifest JSON object。
    :returns: ``(validation_status, diagnostic)``。
    :raises HostDurableError: diagnostic 类型、状态或 reason 非法时抛出。
    """

    raw_diagnostic = value.get("diagnostic")
    if raw_diagnostic is None:
        return ("complete", None)
    diagnostic_object = _required_object(
        raw_diagnostic,
        field_name="manifest diagnostic",
    )
    diagnostic = runner_call_hot_diagnostic_from_json(diagnostic_object)
    if diagnostic.status == "complete":
        raise HostDurableError(
            "complete runner-call manifest diagnostic must be null"
        )
    return (diagnostic.status, diagnostic)


def _parse_compactor_identity(
    value: Mapping[str, JsonValue],
) -> RunnerCallCompactorIdentity | None:
    """解析 optional compactor identity。

    :param value: manifest JSON object。
    :returns: typed compactor identity；非 compactor manifest 返回 ``None``。
    :raises HostDurableError: identity 字段集、类型或 digest 非法时抛出。
    """

    raw_identity = value.get("compactor_identity")
    if raw_identity is None:
        return None
    identity = _required_object(
        raw_identity,
        field_name="compactor_identity",
    )
    _require_exact_fields(
        identity,
        expected_fields=_COMPACTOR_IDENTITY_FIELDS,
        field_name="runner-call compactor identity",
    )
    attempt_number = _required_non_negative_int(
        identity,
        "compaction_attempt_number",
    )
    if attempt_number == 0:
        raise HostDurableError(
            "compactor compaction_attempt_number must be positive"
        )
    return RunnerCallCompactorIdentity(
        parent_host_run_id=_required_text(identity, "parent_host_run_id"),
        parent_session_id=_required_text(identity, "parent_session_id"),
        compaction_operation_id=_required_text(
            identity,
            "compaction_operation_id",
        ),
        compactor_engine_run_id=_required_text(
            identity,
            "compactor_engine_run_id",
        ),
        compaction_attempt_number=attempt_number,
        compaction_request_digest=_required_digest(
            identity,
            "compaction_request_digest",
        ),
        compactor_input_projection_ref=_required_text(
            identity,
            "compactor_input_projection_ref",
        ),
    )


def _validate_manifest_graph(manifest: RunnerCallInputManifest) -> None:
    """校验 manifest 内 message/metadata/identity 完整语义图。

    :param manifest: 已完成字段级解析的 typed manifest。
    :returns: ``None``。
    :raises HostDurableError: count/index/role digest、metadata ref 或 compactor
        identity 不闭合时抛出。
    """

    entries = manifest.message_entries
    if manifest.validation_status == "complete" or entries:
        if manifest.message_count != len(entries):
            raise HostDurableError(
                "runner-call manifest message_count does not match message_entries"
            )
    if tuple(entry.index for entry in entries) != tuple(range(len(entries))):
        raise HostDurableError(
            "runner-call manifest message indexes must be contiguous"
        )
    if entries:
        actual_role_digest = runner_role_sequence_digest(
            tuple(entry.role for entry in entries)
        )
        if actual_role_digest != manifest.role_sequence_digest:
            raise HostDurableError(
                "runner-call manifest role_sequence_digest mismatch"
            )
    metadata_ids = frozenset(
        metadata.projector_metadata_id
        for metadata in manifest.projector_metadata
    )
    for entry in entries:
        if entry.projector_metadata_id not in metadata_ids:
            raise HostDurableError(
                "runner-call manifest message projector_metadata_id is dangling"
            )
    is_compactor = manifest.identity.runner_call_kind == "compactor_proposal"
    if is_compactor != (manifest.compactor_identity is not None):
        raise HostDurableError(
            "runner-call manifest compactor identity does not match runner_call_kind"
        )
    compactor_identity = manifest.compactor_identity
    if compactor_identity is not None:
        if (
            compactor_identity.parent_host_run_id
            != manifest.identity.host_run_id
            or compactor_identity.parent_session_id
            != manifest.identity.session_id
        ):
            raise HostDurableError(
                "runner-call manifest compactor parent identity mismatch"
            )
        if (
            compactor_identity.compaction_attempt_number - 1
            != manifest.identity.runner_call_index
        ):
            raise HostDurableError(
                "runner-call manifest compactor attempt/index mismatch"
            )
    diagnostic = manifest.diagnostic
    if diagnostic is not None:
        if (
            diagnostic.observed_count is not None
            and diagnostic.observed_count != manifest.message_count
        ):
            raise HostDurableError(
                "runner-call manifest diagnostic observed_count mismatch"
            )
        if (
            diagnostic.observed_digest is not None
            and diagnostic.observed_digest != manifest.role_sequence_digest
        ):
            raise HostDurableError(
                "runner-call manifest diagnostic observed_digest mismatch"
            )


def _validate_manifest_hot_identity(
    manifest: RunnerCallInputManifest,
    *,
    hot_payload: RunnerCallHotAtoms,
    actual_manifest_digest: str,
) -> None:
    """校验 manifest 与同一 event hot atoms 的所有冗余 identity。

    :param manifest: typed manifest。
    :param hot_payload: typed hot atoms。
    :param actual_manifest_digest: manifest canonical JSON 实际 digest。
    :returns: ``None``。
    :raises HostDurableError: 任一 identity、count、digest 或 projection pair
        分裂时抛出。
    """

    identity = manifest.identity
    manifest_projection = manifest.projection_descriptor
    expected_projection = (
        None
        if manifest_projection is None
        else (
            manifest_projection.payload_ref,
            manifest_projection.payload_digest,
            manifest_projection.payload_size_bytes,
        )
    )
    hot_projection = (
        None
        if hot_payload.runner_call_projection_artifact_ref is None
        else (
            hot_payload.runner_call_projection_artifact_ref,
            hot_payload.runner_call_projection_artifact_digest,
            hot_payload.runner_call_projection_artifact_size_bytes,
        )
    )
    expected_values = (
        identity.session_id,
        identity.host_run_id,
        identity.attempt_id,
        identity.execution_id,
        identity.runner_call_index,
        identity.runner_call_kind,
        identity.runner_call_trigger_reason,
        identity.iteration_id,
        identity.iteration_index,
        identity.schema_version,
        manifest.validation_status,
        manifest.message_count,
        manifest.role_sequence_digest,
        manifest.input_projection_digest,
        expected_projection,
        actual_manifest_digest,
    )
    hot_values = (
        hot_payload.session_id,
        hot_payload.host_run_id,
        hot_payload.attempt_id,
        hot_payload.execution_id,
        hot_payload.runner_call_index,
        hot_payload.runner_call_kind,
        hot_payload.runner_call_trigger_reason,
        hot_payload.iteration_id,
        hot_payload.iteration_index,
        hot_payload.manifest_schema_version,
        hot_payload.validation_status,
        hot_payload.message_count,
        hot_payload.role_sequence_digest,
        hot_payload.input_projection_digest,
        hot_projection,
        hot_payload.manifest_digest,
    )
    if expected_values != hot_values:
        raise HostDurableError("runner-call hot/manifest identity mismatch")


def _validate_hot_atoms(atoms: RunnerCallHotAtoms) -> None:
    """校验 runner-call hot atoms 的跨字段不变量。

    :param atoms: 待校验 atoms。
    :returns: ``None``。
    :raises HostDurableError: 任一字段或 descriptor pair 非法时抛出。
    """

    for field_name, value in (
        ("session_id", atoms.session_id),
        ("host_run_id", atoms.host_run_id),
        ("runner_call_kind", atoms.runner_call_kind),
        ("runner_call_trigger_reason", atoms.runner_call_trigger_reason),
        ("manifest_payload_ref", atoms.manifest_payload_ref),
        ("manifest_schema_version", atoms.manifest_schema_version),
        ("validation_status", atoms.validation_status),
    ):
        _require_non_empty_text(value, field_name=field_name)
    _require_closed_text(
        atoms.runner_call_kind,
        allowed_values=_RUNNER_CALL_KINDS,
        field_name="runner_call_kind",
    )
    _require_closed_text(
        atoms.runner_call_trigger_reason,
        allowed_values=_RUNNER_CALL_TRIGGER_REASONS,
        field_name="runner_call_trigger_reason",
    )
    _require_closed_text(
        atoms.validation_status,
        allowed_values=_RUNNER_CALL_VALIDATION_STATUSES,
        field_name="validation_status",
    )
    if atoms.manifest_schema_version != RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION:
        raise HostDurableError(
            "runner-call manifest schema version is unsupported"
        )
    for field_name, value in (
        ("attempt_id", atoms.attempt_id),
        ("execution_id", atoms.execution_id),
        ("iteration_id", atoms.iteration_id),
    ):
        _require_optional_non_empty_text(value, field_name=field_name)
    if (atoms.attempt_id is None) != (atoms.execution_id is None):
        raise HostDurableError("runner-call attempt_id/execution_id must pair")
    if (atoms.iteration_id is None) != (atoms.iteration_index is None):
        raise HostDurableError("runner-call iteration_id/iteration_index must pair")
    for field_name, value in (
        ("runner_call_index", atoms.runner_call_index),
        ("message_count", atoms.message_count),
    ):
        _require_non_negative_int(value, field_name=field_name)
    _require_optional_non_negative_int(
        atoms.iteration_index,
        field_name="iteration_index",
    )
    for field_name, value in (
        ("manifest_digest", atoms.manifest_digest),
        ("role_sequence_digest", atoms.role_sequence_digest),
        ("input_projection_digest", atoms.input_projection_digest),
    ):
        _require_digest(value, field_name=field_name)
    projection_fields = (
        atoms.runner_call_projection_artifact_ref,
        atoms.runner_call_projection_artifact_digest,
        atoms.runner_call_projection_artifact_size_bytes,
    )
    if any(value is None for value in projection_fields) and not all(
        value is None for value in projection_fields
    ):
        raise HostDurableError(
            "runner-call projection descriptor ref/digest/size must pair"
        )
    if atoms.runner_call_projection_artifact_ref is not None:
        _require_non_empty_text(
            atoms.runner_call_projection_artifact_ref,
            field_name="runner_call_projection_artifact_ref",
        )
    if atoms.runner_call_projection_artifact_digest is not None:
        _require_digest(
            atoms.runner_call_projection_artifact_digest,
            field_name="runner_call_projection_artifact_digest",
        )
    _require_optional_non_negative_int(
        atoms.runner_call_projection_artifact_size_bytes,
        field_name="runner_call_projection_artifact_size_bytes",
    )
    _validate_diagnostic(atoms.diagnostic)
    if atoms.diagnostic.status != atoms.validation_status:
        raise HostDurableError("runner-call validation status and diagnostic mismatch")
    if atoms.validation_status == "complete":
        if (
            atoms.diagnostic.observed_count != atoms.message_count
            or atoms.diagnostic.expected_count != atoms.message_count
        ):
            raise HostDurableError(
                "complete runner-call diagnostic message_count mismatch"
            )
        if (
            atoms.diagnostic.observed_digest != atoms.role_sequence_digest
            or atoms.diagnostic.expected_digest != atoms.role_sequence_digest
        ):
            raise HostDurableError(
                "complete runner-call diagnostic role_sequence_digest mismatch"
            )
        return
    if (
        atoms.diagnostic.observed_count is not None
        and atoms.diagnostic.observed_count != atoms.message_count
    ):
        raise HostDurableError("runner-call diagnostic observed_count mismatch")
    if (
        atoms.diagnostic.observed_digest is not None
        and atoms.diagnostic.observed_digest != atoms.role_sequence_digest
    ):
        raise HostDurableError("runner-call diagnostic observed_digest mismatch")


def _validate_diagnostic(diagnostic: RunnerCallHotDiagnostic) -> None:
    """校验固定 diagnostic atoms。

    :param diagnostic: 待校验 diagnostic。
    :returns: ``None``。
    :raises HostDurableError: 字段类型、数量或 digest 非法时抛出。
    """

    _require_non_empty_text(diagnostic.status, field_name="diagnostic.status")
    _require_closed_text(
        diagnostic.status,
        allowed_values=_RUNNER_CALL_VALIDATION_STATUSES,
        field_name="diagnostic.status",
    )
    _require_non_empty_text(
        diagnostic.consumer_boundary,
        field_name="diagnostic.consumer_boundary",
    )
    for field_name, value in (
        ("diagnostic.reason", diagnostic.reason),
        ("diagnostic.missing_atom_kind", diagnostic.missing_atom_kind),
        ("diagnostic.missing_ref_kind", diagnostic.missing_ref_kind),
        ("diagnostic.missing_ref", diagnostic.missing_ref),
    ):
        _require_optional_non_empty_text(value, field_name=field_name)
    if diagnostic.status == "complete":
        if any(
            value is not None
            for value in (
                diagnostic.reason,
                diagnostic.missing_atom_kind,
                diagnostic.missing_ref_kind,
                diagnostic.missing_ref,
            )
        ):
            raise HostDurableError(
                "complete runner-call diagnostic cannot carry missing/reason fields"
            )
    else:
        if diagnostic.reason is None:
            raise HostDurableError(
                "non-complete runner-call diagnostic reason is required"
            )
        _require_closed_text(
            diagnostic.reason,
            allowed_values=_RUNNER_CALL_DIAGNOSTIC_REASONS,
            field_name="diagnostic.reason",
        )
    if diagnostic.missing_atom_kind is not None:
        _require_closed_text(
            diagnostic.missing_atom_kind,
            allowed_values=_RUNNER_CALL_MISSING_ATOM_KINDS,
            field_name="diagnostic.missing_atom_kind",
        )
    if diagnostic.missing_ref_kind is not None:
        _require_closed_text(
            diagnostic.missing_ref_kind,
            allowed_values=_RUNNER_CALL_MISSING_REF_KINDS,
            field_name="diagnostic.missing_ref_kind",
        )
    _require_optional_non_negative_int(
        diagnostic.observed_count,
        field_name="diagnostic.observed_count",
    )
    _require_optional_non_negative_int(
        diagnostic.expected_count,
        field_name="diagnostic.expected_count",
    )
    if diagnostic.observed_digest is not None:
        _require_digest(
            diagnostic.observed_digest,
            field_name="diagnostic.observed_digest",
        )
    if diagnostic.expected_digest is not None:
        _require_digest(
            diagnostic.expected_digest,
            field_name="diagnostic.expected_digest",
        )
    if diagnostic.status == "complete":
        if (
            diagnostic.observed_count is None
            or diagnostic.expected_count is None
            or diagnostic.observed_digest is None
            or diagnostic.expected_digest is None
        ):
            raise HostDurableError(
                "complete runner-call diagnostic count/digest fields are required"
            )
        if diagnostic.observed_count != diagnostic.expected_count:
            raise HostDurableError(
                "complete runner-call diagnostic count fields mismatch"
            )
        if diagnostic.observed_digest != diagnostic.expected_digest:
            raise HostDurableError(
                "complete runner-call diagnostic digest fields mismatch"
            )


def _require_exact_fields(
    value: Mapping[str, JsonValue],
    *,
    expected_fields: frozenset[str],
    field_name: str,
) -> None:
    """校验 JSON object 字段集合完全等于 closed contract。

    :param value: JSON object。
    :param expected_fields: 精确允许字段集合。
    :param field_name: 错误上下文字段名。
    :returns: ``None``。
    :raises HostDurableError: 字段缺失或出现未知字段时抛出。
    """

    if frozenset(value) != expected_fields:
        raise HostDurableError(f"{field_name} fields mismatch")


def _required_object(
    value: JsonValue,
    *,
    field_name: str,
) -> Mapping[str, JsonValue]:
    """读取必填 JSON object。

    :param value: 待校验 JSON 值。
    :param field_name: 错误上下文字段名。
    :returns: JSON object。
    :raises HostDurableError: 值不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise HostDurableError(f"{field_name} must be object")
    return cast(Mapping[str, JsonValue], value)


def _required_array(
    value: Mapping[str, JsonValue],
    field_name: str,
) -> list[JsonValue]:
    """读取 JSON object 的必填数组。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: JSON array。
    :raises HostDurableError: 字段不是数组时抛出。
    """

    raw_array = value.get(field_name)
    if not isinstance(raw_array, list):
        raise HostDurableError(f"{field_name} must be array")
    return cast(list[JsonValue], raw_array)


def _text_tuple(
    value: Mapping[str, JsonValue],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    """读取必填非空文本数组。

    :param value: JSON object。
    :param field_name: 字段名。
    :param allow_empty: 是否允许空数组。
    :returns: 文本元组。
    :raises HostDurableError: 数组、元素或空值策略非法时抛出。
    """

    raw_items = _required_array(value, field_name)
    if not allow_empty and not raw_items:
        raise HostDurableError(f"{field_name} must not be empty")
    items: list[str] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, str) or raw_item.strip() == "":
            raise HostDurableError(f"{field_name} item must be non-empty text")
        items.append(raw_item)
    return tuple(items)


def _required_non_negative_int(
    value: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取 JSON object 的必填非负整数。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises HostDurableError: 字段缺失或不是非负整数时抛出。
    """

    item = value.get(field_name)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise HostDurableError(f"{field_name} must be non-negative integer")
    return item


def _required_digest(
    value: Mapping[str, JsonValue],
    field_name: str,
) -> str:
    """读取 JSON object 的必填 sha256 digest。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: Host sha256 digest。
    :raises HostDurableError: 字段缺失或 digest 格式非法时抛出。
    """

    item = _required_text(value, field_name)
    _require_digest(item, field_name=field_name)
    return item


def _require_closed_text(
    value: str,
    *,
    allowed_values: frozenset[str],
    field_name: str,
) -> None:
    """校验文本属于 closed enum。

    :param value: 待校验文本。
    :param allowed_values: closed enum 值集合。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 文本不在 closed enum 中时抛出。
    """

    if value not in allowed_values:
        raise HostDurableError(f"{field_name} is unsupported")


def _required_text(value: Mapping[str, JsonValue], field_name: str) -> str:
    """读取 JSON object 的必填非空文本。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段缺失、非文本或为空时抛出。
    """

    item = value.get(field_name)
    if not isinstance(item, str) or item.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")
    return item


def _optional_text(
    value: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 JSON object 的可选非空文本。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但非文本或为空时抛出。
    """

    item = value.get(field_name)
    if item is None:
        return None
    if not isinstance(item, str) or item.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text when provided")
    return item


def _optional_non_negative_int(
    value: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """读取 JSON object 的可选非负整数。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 非负整数或 ``None``。
    :raises HostDurableError: 字段存在但不是非负整数时抛出。
    """

    item = value.get(field_name)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise HostDurableError(f"{field_name} must be non-negative integer")
    return item


def _optional_digest(
    value: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 JSON object 的可选 Host sha256 digest。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: digest 或 ``None``。
    :raises HostDurableError: 字段存在但不是标准 digest 时抛出。
    """

    item = _optional_text(value, field_name)
    if item is not None:
        _require_digest(item, field_name=field_name)
    return item


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验必填非空文本。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 值非文本或为空时抛出。
    """

    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")


def _require_optional_non_empty_text(
    value: str | None, *, field_name: str
) -> None:
    """校验可选非空文本。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 非 ``None`` 值为空时抛出。
    """

    if value is not None:
        _require_non_empty_text(value, field_name=field_name)


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验严格非负整数。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 值不是严格非负整数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"{field_name} must be non-negative integer")


def _require_optional_non_negative_int(
    value: int | None, *, field_name: str
) -> None:
    """校验可选严格非负整数。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 非 ``None`` 值不是严格非负整数时抛出。
    """

    if value is not None:
        _require_non_negative_int(value, field_name=field_name)


def _require_digest(value: str, *, field_name: str) -> None:
    """校验标准 Host sha256 digest。

    :param value: 待校验 digest。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: digest 格式非法时抛出。
    """

    if not isinstance(value, str) or not is_sha256_digest(value):
        raise HostDurableError(f"{field_name} must be sha256 digest")


__all__ = [
    "complete_runner_call_hot_diagnostic",
    "parse_runner_call_hot_payload",
    "parse_runner_call_manifest",
    "runner_call_hot_diagnostic_from_json",
    "runner_call_hot_payload",
    "runner_call_projector_metadata_descriptor",
    "RunnerCallHotAtoms",
    "RunnerCallHotDiagnostic",
    "RunnerCallInputManifest",
    "RunnerCallManifestIdentity",
    "RunnerCallMessageEntry",
    "RunnerCallProjectorMetadata",
    "RunnerCallProjectionDescriptor",
]
