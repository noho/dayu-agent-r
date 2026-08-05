"""Host proactive compaction durable single-operation 状态 owner。

本模块从 EventLog canonical facts 与完整 runner-call manifest 重建单个 Run 的
proactive compaction phase、冻结输入、全局 attempt 使用量与下一步 decision。
dispatcher 只消费这里的 typed projection，不再按 committed request 数量反推
operation uniqueness，也不提供旧 count fallback。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host._event_payload import payload_object
from dayu.host.context_event_payload import resolve_context_compacted_payload
from dayu.host._runner_call_manifest import (
    parse_runner_call_hot_payload,
    parse_runner_call_manifest,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    validate_context_compaction_attempt_rejected_payload,
    validate_context_compaction_failed_payload,
    validate_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.compaction import CompactionRequest
from dayu.host.compaction_terminal import (
    CompactionOperationTerminalDisposition,
    CompactionTerminalClosed,
    CompactionTerminalCommitPermit,
    begin_compaction_terminal_commit_in_transaction,
)
from dayu.host.durable.codec import is_sha256_digest
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventLogRow, EventLogStore
from dayu.host.durable.payload_resolution import resolve_json_payload
from dayu.host.durable.transaction import HostTransaction

_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_RUNNER_CALL_KIND_COMPACTOR_PROPOSAL = "compactor_proposal"
_READ_PAGE_SIZE = 64
_OPERATION_EVENT_TYPES = (
    CONTEXT_COMPACTION_REQUESTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_FAILED,
    _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
)


class ProactiveCompactionPhase(StrEnum):
    """proactive durable operation 的封闭 phase。"""

    ABSENT = "absent"
    INCOMPLETE = "incomplete"
    COMPACTED = "compacted"
    FAILED = "failed"
    INVALID = "invalid"


class ProactiveCompactionDecision(StrEnum):
    """dispatcher 可执行的封闭 decision。"""

    CREATE_NEW = "create_new"
    RESUME_EXISTING = "resume_existing"
    USE_COMPACTED = "use_compacted"
    USE_FAILED_FALLBACK = "use_failed_fallback"
    FAIL_EXISTING_OPERATION = "fail_existing_operation"


class ProactiveCompactionAttemptStage(StrEnum):
    """proactive global attempt 对应的确定性 request 阶段。"""

    ROOT = "root"
    ROOT_REPAIR = "root_repair"
    TIER_1_FALLBACK_CAPS = "tier_1_fallback_caps"
    TIER_2_SECTION_DEGRADE = "tier_2_section_degrade"
    TIER_3_DELTA_ONLY = "tier_3_delta_only"


@dataclass(frozen=True, slots=True)
class ProactiveCompactionTierRequest:
    """可用 recovery tier 与其 immutable request。

    :param stage: tier 1-3 中的精确阶段。
    :param request: pipeline 为该 tier 构造的 request。
    """

    stage: ProactiveCompactionAttemptStage
    request: CompactionRequest


@dataclass(frozen=True, slots=True)
class ProactiveCompactionAttemptPlan:
    """单个全局 attempt 的 frozen stage/request 计划。

    :param attempt_number: operation 内全局连续 attempt number。
    :param stage: root initial、root repair 或 tier 1-3。
    :param request: 该 attempt 唯一允许使用的 immutable request。
    """

    attempt_number: int
    stage: ProactiveCompactionAttemptStage
    request: CompactionRequest


@dataclass(frozen=True, slots=True)
class _PreparedProactiveManifest:
    """单个 proactive attempt 的 durable proposal manifest identity。

    :param event_sequence: manifest canonical event sequence。
    :param manifest_payload_ref: 完整 runner-call manifest payload ref。
    :param manifest_digest: 完整 runner-call manifest digest。
    :param request_digest: 该阶段 immutable compaction request digest。
    """

    event_sequence: int
    manifest_payload_ref: str
    manifest_digest: str
    request_digest: str


@dataclass(frozen=True, slots=True)
class _CompactionOperationOwner:
    """同一 Run 内一个 strict requested operation 的 owner identity。

    :param trigger_source: proactive 或 reactive trigger source。
    :param request_event_sequence: operation request canonical sequence。
    """

    trigger_source: ContextCompactionTriggerSource
    request_event_sequence: int


def build_proactive_compaction_attempt_schedule(
    *,
    root_request: CompactionRequest,
    tier_requests: tuple[ProactiveCompactionTierRequest, ...],
    max_attempt_number: int,
) -> tuple[ProactiveCompactionAttemptPlan, ...]:
    """按 frozen max 构造 root repair 与可用 tier 的唯一 attempt schedule。

    每个可用 tier 最多保留一个尾部 slot；预算剩余前缀全部复用 root
    immutable request，第一个为 root initial，其余为 whole-candidate repair。
    预算不足时在保留 root 后按 tier 1→2→3 顺序截断。

    :param root_request: normal/root immutable request。
    :param tier_requests: pipeline 按 tier 1→2→3 构造的可用 requests。
    :param max_attempt_number: operation frozen semantic budget。
    :returns: 长度精确等于 frozen max 的连续 attempt plans。
    :raises TypeError: request 或 tier 类型非法时抛出。
    :raises ValueError: budget、tier 阶段或顺序非法时抛出。
    """

    if not isinstance(root_request, CompactionRequest):
        raise TypeError("root_request must be CompactionRequest")
    if isinstance(max_attempt_number, bool) or not isinstance(
        max_attempt_number, int
    ):
        raise TypeError("max_attempt_number must be int")
    if max_attempt_number <= 0:
        raise ValueError("max_attempt_number must be positive")
    allowed_tier_order = (
        ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS,
        ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE,
        ProactiveCompactionAttemptStage.TIER_3_DELTA_ONLY,
    )
    previous_index = -1
    for tier_request in tier_requests:
        if not isinstance(tier_request, ProactiveCompactionTierRequest):
            raise TypeError(
                "tier_requests items must be ProactiveCompactionTierRequest"
            )
        if tier_request.stage not in allowed_tier_order:
            raise ValueError("tier request stage must be tier 1-3")
        tier_index = allowed_tier_order.index(tier_request.stage)
        if tier_index <= previous_index:
            raise ValueError("tier requests must follow unique tier 1-3 order")
        previous_index = tier_index
    selected_tiers = tier_requests[: max(0, max_attempt_number - 1)]
    root_attempt_count = max_attempt_number - len(selected_tiers)
    plans: list[ProactiveCompactionAttemptPlan] = []
    for attempt_number in range(1, root_attempt_count + 1):
        plans.append(
            ProactiveCompactionAttemptPlan(
                attempt_number=attempt_number,
                stage=(
                    ProactiveCompactionAttemptStage.ROOT
                    if attempt_number == 1
                    else ProactiveCompactionAttemptStage.ROOT_REPAIR
                ),
                request=root_request,
            )
        )
    for tier_request in selected_tiers:
        plans.append(
            ProactiveCompactionAttemptPlan(
                attempt_number=len(plans) + 1,
                stage=tier_request.stage,
                request=tier_request.request,
            )
        )
    return tuple(plans)


@dataclass(frozen=True, slots=True)
class ProactiveCompactionState:
    """从 canonical facts 投影出的 proactive operation 状态。

    :param phase: 当前 durable phase。
    :param operation_id: request event 同源 operation id；ABSENT 时为 ``None``。
    :param input_snapshot_cursor: request 冻结输入 cursor。
    :param max_attempt_number: request 冻结的全局 attempt 上限。
    :param frozen_material_list_digest: request 冻结 material digest。
    :param frozen_material_refs: request 冻结 material refs。
    :param prepared_attempt_numbers: 已写 proposal manifest 的 attempts。
    :param rejected_attempt_numbers: 已写 rejection 的 attempts。
    :param next_attempt_number: 保守计入 prepared/rejected 后的下一 attempt。
    :param compacted_event_sequence: accepted terminal sequence；INVALID 时保留已见
        raw terminal 证据，供 dispatcher 避免追加第二 terminal。
    :param failed_event_sequence: failed terminal sequence；INVALID 时保留已见 raw
        terminal 证据，供 dispatcher 避免追加第二 terminal。
    :param prepared_request_digests: 每个 prepared attempt 与其 tier request digest。
    :param invalid_reason: INVALID phase 的稳定原因。
    """

    phase: ProactiveCompactionPhase
    operation_id: str | None
    input_snapshot_cursor: int | None
    max_attempt_number: int | None
    frozen_material_list_digest: str | None
    frozen_material_refs: tuple[str, ...]
    prepared_attempt_numbers: tuple[int, ...]
    rejected_attempt_numbers: tuple[int, ...]
    next_attempt_number: int | None
    compacted_event_sequence: int | None
    failed_event_sequence: int | None
    prepared_request_digests: tuple[tuple[int, str], ...]
    invalid_reason: str | None


@dataclass(frozen=True, slots=True)
class ProactiveCompactionProjection:
    """typed state 与唯一 dispatcher decision。

    :param state: durable operation 状态。
    :param decision: 由 phase 与 remaining budget 唯一派生的 decision。
    """

    state: ProactiveCompactionState
    decision: ProactiveCompactionDecision


def validate_proactive_compaction_attempt_schedule(
    state: ProactiveCompactionState,
    schedule: tuple[ProactiveCompactionAttemptPlan, ...],
) -> None:
    """验证 prepared manifests 与重建后的 frozen stage/request schedule 同源。

    :param state: canonical facts 投影出的 operation state。
    :param schedule: 同一 frozen material/max 重建的 attempt schedule。
    :returns: ``None``。
    :raises RuntimeError: budget、attempt number 或 request digest 不匹配时抛出。
    """

    if state.max_attempt_number is None:
        raise RuntimeError("proactive state is missing frozen attempt budget")
    if len(schedule) != state.max_attempt_number:
        raise RuntimeError("proactive attempt schedule budget changed")
    expected_by_attempt = {plan.attempt_number: plan for plan in schedule}
    for attempt_number, request_digest in state.prepared_request_digests:
        expected = expected_by_attempt.get(attempt_number)
        if expected is None:
            raise RuntimeError("proactive prepared attempt is outside schedule")
        if expected.request.digest() != request_digest:
            raise RuntimeError(
                "proactive prepared attempt request digest changed for stage"
            )


def read_proactive_compaction_projection(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    run_id: str,
) -> ProactiveCompactionProjection:
    """重建目标 Run 的 proactive compaction durable projection。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog 读取 primitive。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :returns: typed state 与 decision。
    :raises ValueError: Session 或 Run id 为空时抛出。
    """

    if session_id.strip() == "":
        raise ValueError("session_id must be non-empty")
    if run_id.strip() == "":
        raise ValueError("run_id must be non-empty")
    rows = _read_operation_rows(transaction, event_log_store, run_id=run_id)
    operation_id = _earliest_safe_proactive_operation_id(
        rows,
        session_id=session_id,
        run_id=run_id,
    )
    try:
        terminal_state: (
            CompactionTerminalCommitPermit | CompactionTerminalClosed | None
        ) = None
        if operation_id is not None:
            terminal_state = begin_compaction_terminal_commit_in_transaction(
                transaction,
                event_log_store,
                operation_id=operation_id,
                expected_trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            if (
                isinstance(terminal_state, CompactionTerminalClosed)
                and terminal_state.disposition
                is CompactionOperationTerminalDisposition.INVALID_MULTIPLE
            ):
                raise HostDurableError("multiple proactive compaction terminals")
        state = _project_state(
            transaction,
            rows,
            session_id=session_id,
            run_id=run_id,
            terminal_state=terminal_state,
        )
    except (HostDurableError, TypeError, ValueError) as exc:
        compacted_sequence, failed_sequence = _terminal_evidence(rows)
        state = _invalid_state(
            operation_id=operation_id,
            reason=exc.__class__.__name__,
            compacted_event_sequence=compacted_sequence,
            failed_event_sequence=failed_sequence,
        )
    return ProactiveCompactionProjection(
        state=state,
        decision=_decision_from_state(state),
    )


def _read_operation_rows(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run_id: str,
) -> tuple[EventLogRow, ...]:
    """按 bounded page 读取 operation 相关 canonical rows。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param run_id: 目标 Run id。
    :returns: 全部相关 rows 的稳定 sequence 顺序元组。
    :raises HostDurableError: durable 读取失败时抛出。
    """

    cursor = 0
    rows: list[EventLogRow] = []
    while True:
        page = event_log_store.read_run_events_by_types_page(
            transaction,
            run_id=run_id,
            event_types=_OPERATION_EVENT_TYPES,
            after_event_sequence=cursor,
            limit=_READ_PAGE_SIZE,
        )
        rows.extend(page)
        if len(page) < _READ_PAGE_SIZE:
            return tuple(rows)
        cursor = page[-1].event_sequence


def _project_state(
    transaction: HostTransaction,
    rows: tuple[EventLogRow, ...],
    *,
    session_id: str,
    run_id: str,
    terminal_state: (
        CompactionTerminalCommitPermit | CompactionTerminalClosed | None
    ),
) -> ProactiveCompactionState:
    """从已排序 rows 严格投影 proactive state。

    :param transaction: 当前 Host transaction。
    :param rows: operation 相关 canonical rows。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :param terminal_state: shared terminal owner 的 transaction-local fresh 结果。
    :returns: durable state。
    :raises HostDurableError: canonical identity 或 payload 不变量损坏时抛出。
    """

    requested_rows: list[tuple[EventLogRow, Mapping[str, JsonValue]]] = []
    operation_owners: dict[str, _CompactionOperationOwner] = {}
    for row in rows:
        if row.session_id != session_id or row.run_id != run_id:
            raise HostDurableError("proactive operation row identity mismatch")
        if row.event_type != CONTEXT_COMPACTION_REQUESTED:
            continue
        payload, operation_id, owner = _validated_request_owner(
            row,
            session_id=session_id,
            run_id=run_id,
        )
        if operation_id in operation_owners:
            raise HostDurableError("duplicate compaction operation id")
        operation_owners[operation_id] = owner
        if owner.trigger_source is ContextCompactionTriggerSource.PROACTIVE:
            requested_rows.append((row, payload))
    if len(requested_rows) > 1:
        raise HostDurableError("multiple proactive compaction requests")

    operation_id: str | None = None
    max_attempt_number: int | None = None
    input_snapshot_cursor: int | None = None
    frozen_digest: str | None = None
    frozen_refs: tuple[str, ...] = ()
    if requested_rows:
        _, request_payload = requested_rows[0]
        operation_id = _required_text(request_payload, "operation_id")
        max_attempt_number = _required_positive_int(
            request_payload,
            "max_compaction_attempts_per_operation",
        )
        input_snapshot_cursor = _required_non_negative_int(
            request_payload,
            "input_snapshot_cursor",
        )
        frozen_digest = _required_text(
            request_payload,
            "frozen_material_list_digest",
        )
        if not is_sha256_digest(frozen_digest):
            raise HostDurableError("proactive frozen material digest is invalid")
        frozen_refs = _required_text_tuple(
            request_payload,
            "frozen_material_refs",
        )

    prepared_attempts: set[int] = set()
    rejected_attempts: set[int] = set()
    prepared_manifests: dict[int, _PreparedProactiveManifest] = {}
    compacted_sequence: int | None = None
    failed_sequence: int | None = None
    terminal_sequence = (
        terminal_state.first_terminal_event_sequence
        if isinstance(terminal_state, CompactionTerminalClosed)
        else None
    )
    for row in rows:
        if row.event_type == CONTEXT_COMPACTION_REQUESTED:
            continue
        payload = (
            resolve_context_compacted_payload(transaction, row)
            if row.event_type == CONTEXT_COMPACTED
            else payload_object(row)
        )
        if row.event_type == _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED:
            hot = parse_runner_call_hot_payload(payload)
            if hot.runner_call_kind != _RUNNER_CALL_KIND_COMPACTOR_PROPOSAL:
                continue
            resolved = resolve_json_payload(
                transaction,
                payload_ref=hot.manifest_payload_ref,
                expected_digest=hot.manifest_digest,
            )
            manifest = parse_runner_call_manifest(
                resolved.payload,
                hot_payload=hot,
            )
            identity = manifest.compactor_identity
            if identity is None:
                raise HostDurableError(
                    "compactor proposal manifest is missing compactor identity"
                )
            if (
                identity.parent_session_id != session_id
                or identity.parent_host_run_id != run_id
            ):
                raise HostDurableError("proactive manifest identity mismatch")
            manifest_owner = _required_operation_owner(
                operation_owners,
                operation_id=identity.compaction_operation_id,
                row_sequence=row.event_sequence,
                row_kind="manifest",
            )
            if (
                manifest_owner.trigger_source
                is ContextCompactionTriggerSource.REACTIVE
            ):
                continue
            if operation_id is None or max_attempt_number is None:
                raise HostDurableError(
                    "proactive manifest is missing proactive request owner"
                )
            if identity.compaction_operation_id != operation_id:
                raise HostDurableError(
                    "manifest belongs to a second proactive operation"
                )
            attempt_number = identity.compaction_attempt_number
            if (
                terminal_sequence is not None
                and row.event_sequence > terminal_sequence
            ):
                raise HostDurableError(
                    "proactive manifest was appended after operation terminal"
                )
            if attempt_number in rejected_attempts:
                raise HostDurableError(
                    "proactive manifest was appended after attempt rejection"
                )
            existing_manifest = prepared_manifests.get(attempt_number)
            if existing_manifest is not None:
                if existing_manifest.request_digest != identity.compaction_request_digest:
                    raise HostDurableError(
                        "proactive prepared attempt request digest conflicts"
                    )
                continue
            _add_attempt_number(
                prepared_attempts,
                attempt_number,
                max_attempt_number=max_attempt_number,
                kind="prepared",
            )
            prepared_manifests[attempt_number] = _PreparedProactiveManifest(
                event_sequence=row.event_sequence,
                manifest_payload_ref=hot.manifest_payload_ref,
                manifest_digest=hot.manifest_digest,
                request_digest=identity.compaction_request_digest,
            )
            continue
        if row.event_type == CONTEXT_COMPACTION_ATTEMPT_REJECTED:
            validate_context_compaction_attempt_rejected_payload(payload)
            row_operation_id = _required_text(payload, "operation_id")
            row_owner = _required_operation_owner(
                operation_owners,
                operation_id=row_operation_id,
                row_sequence=row.event_sequence,
                row_kind="rejection",
            )
            if row_owner.trigger_source is ContextCompactionTriggerSource.REACTIVE:
                continue
            if operation_id is None or max_attempt_number is None:
                raise HostDurableError(
                    "proactive rejection is missing proactive request owner"
                )
            if row_operation_id != operation_id:
                raise HostDurableError(
                    "rejection belongs to a second proactive operation"
                )
            if (
                terminal_sequence is not None
                and row.event_sequence > terminal_sequence
            ):
                raise HostDurableError(
                    "proactive rejection was appended after operation terminal"
                )
            rejected_attempt_number = _required_positive_int(
                payload,
                "attempt_number",
            )
            _validate_rejected_manifest_reference(
                payload,
                attempt_number=rejected_attempt_number,
                prepared_manifest=prepared_manifests.get(
                    rejected_attempt_number
                ),
            )
            _add_attempt_number(
                rejected_attempts,
                rejected_attempt_number,
                max_attempt_number=max_attempt_number,
                kind="rejected",
            )
            continue
        if row.event_type == CONTEXT_COMPACTED:
            row_operation_id = _required_text(payload, "operation_id")
            row_owner = _required_operation_owner(
                operation_owners,
                operation_id=row_operation_id,
                row_sequence=row.event_sequence,
                row_kind="compacted terminal",
            )
            if row_owner.trigger_source is ContextCompactionTriggerSource.REACTIVE:
                continue
            if operation_id is None:
                raise HostDurableError(
                    "proactive compacted terminal is missing proactive request owner"
                )
            if row_operation_id != operation_id:
                raise HostDurableError("proactive compacted operation mismatch")
            if (
                not isinstance(terminal_state, CompactionTerminalClosed)
                or terminal_state.disposition
                is not CompactionOperationTerminalDisposition.COMPACTED
                or terminal_state.first_terminal_event_sequence
                != row.event_sequence
            ):
                raise HostDurableError(
                    "proactive compacted terminal disagrees with terminal owner"
                )
            _validate_compacted_manifest_reference(
                payload,
                prepared_manifests=prepared_manifests,
                rejected_attempts=rejected_attempts,
            )
            compacted_sequence = row.event_sequence
            continue
        if row.event_type == CONTEXT_COMPACTION_FAILED:
            validate_context_compaction_failed_payload(payload)
            row_operation_id = _required_text(payload, "operation_id")
            row_owner = _required_operation_owner(
                operation_owners,
                operation_id=row_operation_id,
                row_sequence=row.event_sequence,
                row_kind="failed terminal",
            )
            if row_owner.trigger_source is ContextCompactionTriggerSource.REACTIVE:
                continue
            if operation_id is None:
                raise HostDurableError(
                    "proactive failed terminal is missing proactive request owner"
                )
            if row_operation_id != operation_id:
                raise HostDurableError("proactive failed operation mismatch")
            if (
                not isinstance(terminal_state, CompactionTerminalClosed)
                or terminal_state.disposition
                is not CompactionOperationTerminalDisposition.FAILED
                or terminal_state.first_terminal_event_sequence
                != row.event_sequence
            ):
                raise HostDurableError(
                    "proactive failed terminal disagrees with terminal owner"
                )
            _validate_failed_attempt_count(
                payload,
                prepared_attempts=prepared_attempts,
                rejected_attempts=rejected_attempts,
            )
            failed_sequence = row.event_sequence
    if operation_id is None:
        return _absent_state()
    if (
        max_attempt_number is None
        or input_snapshot_cursor is None
        or frozen_digest is None
    ):
        raise HostDurableError("proactive request projection is incomplete")

    used_attempts = prepared_attempts | rejected_attempts
    if used_attempts:
        highest_attempt = max(used_attempts)
        if used_attempts != set(range(1, highest_attempt + 1)):
            raise HostDurableError("proactive attempt numbers are not contiguous")
        next_attempt_number = highest_attempt + 1
    else:
        next_attempt_number = 1
    phase = ProactiveCompactionPhase.INCOMPLETE
    if compacted_sequence is not None:
        phase = ProactiveCompactionPhase.COMPACTED
    elif failed_sequence is not None:
        phase = ProactiveCompactionPhase.FAILED
    return ProactiveCompactionState(
        phase=phase,
        operation_id=operation_id,
        input_snapshot_cursor=input_snapshot_cursor,
        max_attempt_number=max_attempt_number,
        frozen_material_list_digest=frozen_digest,
        frozen_material_refs=frozen_refs,
        prepared_attempt_numbers=tuple(sorted(prepared_attempts)),
        rejected_attempt_numbers=tuple(sorted(rejected_attempts)),
        next_attempt_number=next_attempt_number,
        compacted_event_sequence=compacted_sequence,
        failed_event_sequence=failed_sequence,
        prepared_request_digests=tuple(
            sorted(
                (
                    attempt_number,
                    manifest.request_digest,
                )
                for attempt_number, manifest in prepared_manifests.items()
            )
        ),
        invalid_reason=None,
    )


def _required_operation_owner(
    operation_owners: Mapping[str, _CompactionOperationOwner],
    *,
    operation_id: str,
    row_sequence: int,
    row_kind: str,
) -> _CompactionOperationOwner:
    """读取 operation row 对应且时序合法的 strict request owner。

    :param operation_owners: 当前 Run 全部已验证 requested operations。
    :param operation_id: row 声明的 operation id。
    :param row_sequence: row canonical event sequence。
    :param row_kind: 稳定诊断类别。
    :returns: 对应 request owner。
    :raises HostDurableError: operation 未知或 row 早于/等于 request 时抛出。
    """

    owner = operation_owners.get(operation_id)
    if owner is None:
        raise HostDurableError(f"proactive {row_kind} operation is unknown")
    if row_sequence <= owner.request_event_sequence:
        raise HostDurableError(
            f"proactive {row_kind} precedes its operation request"
        )
    return owner


def _validate_rejected_manifest_reference(
    payload: Mapping[str, JsonValue],
    *,
    attempt_number: int,
    prepared_manifest: _PreparedProactiveManifest | None,
) -> None:
    """校验 rejected attempt 与同 attempt proposal manifest 精确关联。

    proposal input 尚未成功 prepare/record 时，producer 合法写入空 manifest
    pair；一旦该 attempt 已有 manifest，则 rejection 必须引用同一 ref/digest。

    :param payload: 已通过 context event validator 的 rejection payload。
    :param attempt_number: rejection 声明的 global attempt number。
    :param prepared_manifest: 该 attempt 已投影的 manifest；没有时为
        ``None``。
    :returns: ``None``。
    :raises HostDurableError: ref/digest 与 prepared truth 不一致时抛出。
    """

    manifest_ref = _optional_text(payload, "proposal_manifest_ref")
    manifest_digest = _optional_text(payload, "proposal_manifest_digest")
    if prepared_manifest is None:
        if manifest_ref is not None or manifest_digest is not None:
            raise HostDurableError(
                "proactive rejection references missing attempt manifest"
            )
        return
    if (
        manifest_ref != prepared_manifest.manifest_payload_ref
        or manifest_digest != prepared_manifest.manifest_digest
    ):
        raise HostDurableError(
            f"proactive rejected attempt {attempt_number} manifest mismatch"
        )


def _validate_compacted_manifest_reference(
    payload: Mapping[str, JsonValue],
    *,
    prepared_manifests: Mapping[int, _PreparedProactiveManifest],
    rejected_attempts: set[int],
) -> None:
    """校验 accepted terminal 与唯一 proposal manifest 精确关联。

    :param payload: 已通过 context event validator 的 compacted payload。
    :param prepared_manifests: operation 内 attempt 到 manifest 的投影 map。
    :param rejected_attempts: 已提交 rejection 的 attempts。
    :returns: ``None``。
    :raises HostDurableError: accepted attempt 缺 manifest、已 rejected、不是
        当前最高 attempt，或 ref/digest 不匹配时抛出。
    """

    accepted_attempt_number = _required_positive_int(
        payload,
        "accepted_attempt_number",
    )
    prepared_manifest = prepared_manifests.get(accepted_attempt_number)
    if prepared_manifest is None:
        raise HostDurableError(
            "proactive accepted attempt is missing proposal manifest"
        )
    if accepted_attempt_number in rejected_attempts:
        raise HostDurableError(
            "proactive accepted attempt was already rejected"
        )
    if accepted_attempt_number != max(prepared_manifests):
        raise HostDurableError(
            "proactive accepted attempt is not latest prepared attempt"
        )
    if (
        _required_text(payload, "accepted_proposal_manifest_ref")
        != prepared_manifest.manifest_payload_ref
        or _required_text(payload, "accepted_proposal_manifest_digest")
        != prepared_manifest.manifest_digest
    ):
        raise HostDurableError(
            "proactive accepted proposal manifest reference mismatch"
        )


def _validate_failed_attempt_count(
    payload: Mapping[str, JsonValue],
    *,
    prepared_attempts: set[int],
    rejected_attempts: set[int],
) -> None:
    """校验 FAILED terminal 精确声明已消费的 global attempt 数。

    failed producer 可以在 provider 前 fail-close，此时合法 count 为零；已有
    prepared/rejected attempt 时，count 必须等于两类 durable truth 的并集大小。

    :param payload: 已通过 context event validator 的 failed payload。
    :param prepared_attempts: 已 durable prepare 的 attempts。
    :param rejected_attempts: 已 durable reject 的 attempts。
    :returns: ``None``。
    :raises HostDurableError: attempt count 与 operation history 不同源时抛出。
    """

    expected_attempt_count = len(prepared_attempts | rejected_attempts)
    if (
        _required_non_negative_int(payload, "attempt_count")
        != expected_attempt_count
    ):
        raise HostDurableError(
            "proactive failed attempt count does not match durable attempts"
        )


def _decision_from_state(
    state: ProactiveCompactionState,
) -> ProactiveCompactionDecision:
    """由 phase 与 frozen remaining budget 派生唯一 decision。

    :param state: proactive durable state。
    :returns: dispatcher decision。
    :raises RuntimeError: state 内部必填字段缺失时抛出。
    """

    if state.phase is ProactiveCompactionPhase.ABSENT:
        return ProactiveCompactionDecision.CREATE_NEW
    if state.phase is ProactiveCompactionPhase.COMPACTED:
        return ProactiveCompactionDecision.USE_COMPACTED
    if state.phase is ProactiveCompactionPhase.FAILED:
        return ProactiveCompactionDecision.USE_FAILED_FALLBACK
    if state.phase is ProactiveCompactionPhase.INVALID:
        return ProactiveCompactionDecision.FAIL_EXISTING_OPERATION
    if state.next_attempt_number is None or state.max_attempt_number is None:
        raise RuntimeError("incomplete proactive state is missing attempt range")
    if state.next_attempt_number > state.max_attempt_number:
        return ProactiveCompactionDecision.FAIL_EXISTING_OPERATION
    return ProactiveCompactionDecision.RESUME_EXISTING


def _add_attempt_number(
    attempts: set[int],
    attempt_number: int,
    *,
    max_attempt_number: int,
    kind: str,
) -> None:
    """校验并加入一个 prepared/rejected attempt number。

    :param attempts: 对应类别的已见 attempt 集合。
    :param attempt_number: 待加入的 attempt number。
    :param max_attempt_number: request 冻结上限。
    :param kind: 诊断类别。
    :returns: ``None``。
    :raises HostDurableError: 重复或越界时抛出。
    """

    if attempt_number > max_attempt_number:
        raise HostDurableError(f"proactive {kind} attempt exceeds frozen budget")
    if attempt_number in attempts:
        raise HostDurableError(f"proactive {kind} attempt is duplicated")
    attempts.add(attempt_number)


def _absent_state() -> ProactiveCompactionState:
    """构造 ABSENT state。

    :returns: 无 operation 的 typed state。
    :raises Exception: 不主动抛出异常。
    """

    return ProactiveCompactionState(
        phase=ProactiveCompactionPhase.ABSENT,
        operation_id=None,
        input_snapshot_cursor=None,
        max_attempt_number=None,
        frozen_material_list_digest=None,
        frozen_material_refs=(),
        prepared_attempt_numbers=(),
        rejected_attempt_numbers=(),
        next_attempt_number=None,
        compacted_event_sequence=None,
        failed_event_sequence=None,
        prepared_request_digests=(),
        invalid_reason=None,
    )


def _invalid_state(
    *,
    operation_id: str | None,
    reason: str,
    compacted_event_sequence: int | None,
    failed_event_sequence: int | None,
) -> ProactiveCompactionState:
    """构造 fail-closed INVALID state。

    :param operation_id: 最早通过 strict owner 校验的 proactive request event id。
    :param reason: 不含 durable 原文的稳定异常类别。
    :param compacted_event_sequence: INVALID history 中最早 compacted sequence。
    :param failed_event_sequence: INVALID history 中最早 failed sequence。
    :returns: INVALID typed state。
    :raises Exception: 不主动抛出异常。
    """

    return ProactiveCompactionState(
        phase=ProactiveCompactionPhase.INVALID,
        operation_id=operation_id,
        input_snapshot_cursor=None,
        max_attempt_number=None,
        frozen_material_list_digest=None,
        frozen_material_refs=(),
        prepared_attempt_numbers=(),
        rejected_attempt_numbers=(),
        next_attempt_number=None,
        compacted_event_sequence=compacted_event_sequence,
        failed_event_sequence=failed_event_sequence,
        prepared_request_digests=(),
        invalid_reason=reason,
    )


def _validated_request_owner(
    row: EventLogRow,
    *,
    session_id: str,
    run_id: str,
) -> tuple[
    Mapping[str, JsonValue],
    str,
    _CompactionOperationOwner,
]:
    """严格解析 request row 的 payload、operation id 与 trigger owner。

    :param row: 待解析的 ``CONTEXT_COMPACTION_REQUESTED`` row。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :returns: strict payload、operation id 与 owner identity。
    :raises HostDurableError: row identity、operation identity 非法时抛出。
    :raises ValueError: request payload schema 或 trigger source 非法时抛出。
    """

    if row.session_id != session_id or row.run_id != run_id:
        raise HostDurableError("proactive operation row identity mismatch")
    payload = payload_object(row)
    validate_context_compaction_requested_payload(payload)
    operation_id = _required_text(payload, "operation_id")
    if operation_id != row.event_id:
        raise HostDurableError(
            "compaction operation id must equal request event id"
        )
    return (
        payload,
        operation_id,
        _CompactionOperationOwner(
            trigger_source=ContextCompactionTriggerSource(
                _required_text(payload, "trigger_source")
            ),
            request_event_sequence=row.event_sequence,
        ),
    )


def _earliest_safe_proactive_operation_id(
    rows: tuple[EventLogRow, ...],
    *,
    session_id: str,
    run_id: str,
) -> str | None:
    """返回最早通过 strict owner 校验的 proactive operation id。

    malformed request 与 reactive request 都不能为 proactive failure 提供
    fallback identity；本 helper 只复用 request owner 的同一 strict parser。

    :param rows: operation 相关 rows。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :returns: 安全 proactive operation id；不存在时为 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for row in rows:
        if row.event_type != CONTEXT_COMPACTION_REQUESTED:
            continue
        try:
            _, operation_id, owner = _validated_request_owner(
                row,
                session_id=session_id,
                run_id=run_id,
            )
        except (HostDurableError, TypeError, ValueError):
            continue
        if owner.trigger_source is ContextCompactionTriggerSource.PROACTIVE:
            return operation_id
    return None


def _terminal_evidence(
    rows: tuple[EventLogRow, ...],
) -> tuple[int | None, int | None]:
    """提取 INVALID history 中最早的 raw terminal sequence 证据。

    本 helper 不解释 terminal payload，也不把损坏事实当作有效 fallback；它只让
    dispatcher 知道不能再追加另一个 operation terminal。

    :param rows: operation 相关 rows。
    :returns: ``(compacted_sequence, failed_sequence)``。
    :raises Exception: 不主动抛出异常。
    """

    compacted_sequence: int | None = None
    failed_sequence: int | None = None
    for row in rows:
        if (
            row.event_type == CONTEXT_COMPACTED
            and compacted_sequence is None
        ):
            compacted_sequence = row.event_sequence
        elif (
            row.event_type == CONTEXT_COMPACTION_FAILED
            and failed_sequence is None
        ):
            failed_sequence = row.event_sequence
    return compacted_sequence, failed_sequence


def _required_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填非空文本字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")
    return value


def _optional_text(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取可选非空文本字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本；字段值为 ``None`` 时返回 ``None``。
    :raises HostDurableError: 字段值不是非空文本或 ``None`` 时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text or null")
    return value


def _required_positive_int(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取必填正整数字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 正整数。
    :raises HostDurableError: 字段非法时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HostDurableError(f"{field_name} must be positive int")
    return value


def _required_non_negative_int(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取必填非负整数字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises HostDurableError: 字段非法时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"{field_name} must be non-negative int")
    return value


def _required_text_tuple(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> tuple[str, ...]:
    """读取必填非空文本数组。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 文本 tuple。
    :raises HostDurableError: 字段不是数组或元素非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise HostDurableError(f"{field_name} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise HostDurableError(f"{field_name} items must be non-empty text")
        result.append(item)
    return tuple(result)


__all__ = [
    "ProactiveCompactionAttemptPlan",
    "ProactiveCompactionAttemptStage",
    "ProactiveCompactionDecision",
    "ProactiveCompactionPhase",
    "ProactiveCompactionProjection",
    "ProactiveCompactionState",
    "ProactiveCompactionTierRequest",
    "build_proactive_compaction_attempt_schedule",
    "read_proactive_compaction_projection",
    "validate_proactive_compaction_attempt_schedule",
]
