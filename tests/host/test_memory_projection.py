"""Host memory projection contracts 与 durable primitive 测试。"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.memory import (
    ConversationMemoryProjectionConsumer,
    MemoryDiagnosticRow,
    MemorySnapshotRow,
    read_latest_memory_snapshot,
    read_memory_diagnostic,
    reset_conversation_memory_projection,
    write_memory_diagnostic,
    write_memory_snapshot_with_checkpoint,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.projection import (
    ProjectionCheckpointRow,
    ProjectionFailureRow,
    read_projection_checkpoint,
    read_projection_failure,
)
from dayu.host.compaction import (
    MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS,
    MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS,
    EvidenceBackedFactKind,
    MinimumPreserveReason,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationContinuityItem,
    ConversationContinuityKind,
    ConversationContinuityView,
    ConversationMemorySnapshot,
    HostNeutralRefKind,
    MemoryClaimStatus,
    MemoryDiagnostic,
    MemoryDiagnosticReason,
    MemoryExcludedReason,
    MemoryIncludedReason,
    MemoryProjectionEvent,
    MemoryProducerKind,
    MemoryProjectionPolicy,
    MemoryProvenanceRef,
    MemorySizeUnits,
    MemorySnapshotCursor,
    OpaqueMemoryRef,
    PinnedStateView,
    EvidenceBackedFactView,
    WorkingAssumptionView,
    build_empty_conversation_memory_snapshot,
    build_conversation_memory_snapshot_from_events,
    calculate_memory_snapshot_digest,
    conversation_memory_snapshot_from_json_value,
    conversation_memory_snapshot_to_json_value,
    digest_memory_projection_policy,
    estimate_memory_size_units,
    project_conversation_memory_event,
)
from dayu.host.memory_repair import (
    catch_up_conversation_memory_projection,
    rebuild_conversation_memory_projection,
)
from dayu.host.projection import ProjectionConsumerId, ProjectionRunner

_CONSUMER_ID = "host.memory.session.v1"
_SESSION_ID = "session-1"
_NOW = "2026-05-16T00:00:00.000000Z"
_OCCURRED_AT = datetime(2026, 5, 16, tzinfo=UTC)
_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_FORBIDDEN_BUSINESS_TERMS = (
    "company",
    "business_line",
    "technology_release",
)
_SMALL_FACT_BUDGET = 2


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts"
        ),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _policy() -> MemoryProjectionPolicy:
    """构造测试用 memory projection policy。

    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        max_pinned_items=8,
        max_evidence_backed_facts=16,
        max_working_assumptions=8,
        recent_raw_turns_floor=2,
        raw_turn_context_ratio=0.125,
        raw_turn_size_floor=1024,
        raw_turn_size_cap=1024,
        history_pool_context_ratio=0.5,
        history_pool_size_floor=4096,
        history_pool_size_cap=4096,
        stable_layer_context_ratio=0.25,
        stable_layer_size_floor=2048,
        stable_layer_size_cap=2048,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
    )


def _low_history_policy() -> MemoryProjectionPolicy:
    """构造低 history pool 预算的测试 policy。

    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        max_pinned_items=8,
        max_evidence_backed_facts=16,
        max_working_assumptions=8,
        recent_raw_turns_floor=2,
        raw_turn_context_ratio=0.125,
        raw_turn_size_floor=1024,
        raw_turn_size_cap=1024,
        history_pool_context_ratio=0.5,
        history_pool_size_floor=3,
        history_pool_size_cap=3,
        stable_layer_context_ratio=0.25,
        stable_layer_size_floor=2048,
        stable_layer_size_cap=2048,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
    )


def _assistant_budget_policy() -> MemoryProjectionPolicy:
    """构造 assistant conclusion 预算竞争测试 policy。

    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        max_pinned_items=8,
        max_evidence_backed_facts=16,
        max_working_assumptions=8,
        recent_raw_turns_floor=1,
        raw_turn_context_ratio=0.125,
        raw_turn_size_floor=1024,
        raw_turn_size_cap=1024,
        history_pool_context_ratio=0.5,
        history_pool_size_floor=4,
        history_pool_size_cap=4,
        stable_layer_context_ratio=0.25,
        stable_layer_size_floor=2048,
        stable_layer_size_cap=2048,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
    )


def _zero_recent_floor_policy() -> MemoryProjectionPolicy:
    """构造 recent raw floor 为 0 的测试 policy。

    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        max_pinned_items=8,
        max_evidence_backed_facts=16,
        max_working_assumptions=8,
        recent_raw_turns_floor=0,
        raw_turn_context_ratio=0.125,
        raw_turn_size_floor=1024,
        raw_turn_size_cap=1024,
        history_pool_context_ratio=0.5,
        history_pool_size_floor=2,
        history_pool_size_cap=2,
        stable_layer_context_ratio=0.25,
        stable_layer_size_floor=2048,
        stable_layer_size_cap=2048,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
    )


def _small_fact_budget_policy() -> MemoryProjectionPolicy:
    """构造 evidence-backed facts 小预算测试 policy。

    :returns: memory projection policy。
    """

    return replace(_policy(), max_evidence_backed_facts=_SMALL_FACT_BUDGET)


def _memory_event(
    *,
    event_sequence: int,
    event_id: str,
    event_type: str,
    payload: dict[str, JsonValue],
    run_id: str | None = "run-1",
    attempt_id: str | None = "attempt-1",
    execution_id: str | None = "execution-1",
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> MemoryProjectionEvent:
    """构造 memory projection 测试 event。

    :param event_sequence: EventLog sequence。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: canonical payload。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param payload_ref: 可选 payload ref。
    :param payload_digest: 可选 payload digest。
    :returns: memory projection event。
    """

    return MemoryProjectionEvent(
        event_sequence=event_sequence,
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT.value,
        event_type=event_type,
        session_id=_SESSION_ID,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        occurred_at=_NOW,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        payload=payload,
    )


def _build_snapshot(
    events: tuple[MemoryProjectionEvent, ...],
    policy: MemoryProjectionPolicy | None = None,
) -> ConversationMemorySnapshot:
    """按测试 events 构造 memory snapshot。

    :param events: projection events。
    :param policy: 可选 memory policy。
    :returns: memory snapshot。
    """

    actual_policy = _policy() if policy is None else policy
    return build_conversation_memory_snapshot_from_events(
        events=events,
        session_id=_SESSION_ID,
        consumer_id=_CONSUMER_ID,
        policy=actual_policy,
        built_at=_NOW,
    )


def _tool_payload(*, summary: str | None) -> dict[str, JsonValue]:
    """构造 TOOL_RESULT_ACCEPTED payload。

    :param summary: 可选 fact summary。
    :returns: payload dict。
    """

    payload: dict[str, JsonValue] = {
        "session_id": _SESSION_ID,
        "run_id": "run-1",
        "attempt_id": "attempt-1",
        "execution_id": "execution-1",
        "tool_call_id": "call-1",
        "tool_name": "filing.lookup",
        "tool_fact_kind": "completed",
        "tool_identity_digest": _DIGEST_A,
        "normalized_arguments_digest": _DIGEST_B,
        "outcome_digest": _DIGEST_A,
        "payload_digest": _DIGEST_B,
        "payload_ref": {
            "payload_ref": "payload-tool-1",
            "payload_digest": _DIGEST_B,
        },
        "tool_call_requested_event_ref": {
            "event_id": "event-tool-requested",
            "event_sequence": 1,
        },
    }
    if summary is not None:
        payload["fact_summary"] = summary
    return payload


def _compact_payload(
    *,
    summary_text: str,
    confirmed_fact_refs: tuple[str, ...] = (),
    pinned_patch: dict[str, JsonValue] | None = None,
    fact_candidates: list[JsonValue] | None = None,
    minimum_preserve_items: list[JsonValue] | None = None,
    canonical_evidence_refs: tuple[str, ...] = ("evidence-1",),
) -> dict[str, JsonValue]:
    """构造测试用 CONTEXT_COMPACTED payload。

    :param summary_text: episode summary 文本。
    :param confirmed_fact_refs: summary 引用的 evidence-backed fact refs。
    :param pinned_patch: 可选 pinned patch candidate。
    :param fact_candidates: 可选 evidence-backed fact candidates。
    :param minimum_preserve_items: 可选 minimum preserve item candidates。
    :param canonical_evidence_refs: compact payload 保留的 canonical evidence refs。
    :returns: compacted canonical payload。
    """

    patch = pinned_patch if pinned_patch is not None else _missing_pinned_patch()
    return {
        "compact_artifact_ref": "compact-artifact:test",
        "compact_artifact_digest": _DIGEST_A,
        "episode_summary_candidate": {
            "candidate_id": "summary-test",
            "summary_text": summary_text,
            "episode_title": "episode",
            "goal": "goal",
            "completed_actions": [],
            "confirmed_fact_refs": list(confirmed_fact_refs),
            "confirmed_fact_summaries": [],
            "user_constraints": [],
            "open_questions": [],
            "next_step": None,
            "tool_finding_refs": list(confirmed_fact_refs),
            "source_event_refs": ["event-input"],
            "evidence_refs": ["evidence-1"],
            "proposed_evidence_backed_fact_refs": [],
        },
        "pinned_state_patch_candidate": patch,
        "evidence_backed_fact_candidates": (
            [] if fact_candidates is None else fact_candidates
        ),
        "minimum_preserve_item_candidates": (
            [] if minimum_preserve_items is None else minimum_preserve_items
        ),
        "preservation_evidence": [
            {
                "evidence_id": "evidence-1",
                "material_source_refs": ["event-input"],
                "canonical_evidence_refs": list(canonical_evidence_refs),
                "evidence_backed_fact_refs": list(confirmed_fact_refs),
                "memory_snapshot_cursor": None,
                "compact_input_range": None,
            }
        ],
        "preserved_fact_refs": {
            "canonical_evidence_refs": list(canonical_evidence_refs),
            "evidence_backed_fact_refs": list(confirmed_fact_refs),
        },
        "dropped_ranges": [],
        "summarized_ranges": [],
        "evidence_anchors_retained": True,
        "quality_check_result": {
            "accepted": True,
            "rejection_reasons": [],
            "current_user_input_retained": True,
            "canonical_evidence_refs_retained": True,
            "evidence_backed_fact_candidates_accepted": True,
            "minimum_preserve_items_accepted": True,
            "evidence_anchors_retained": True,
            "open_questions_retained": True,
            "retained_canonical_evidence_refs": list(canonical_evidence_refs),
            "dropped_ranges": [],
            "summarized_ranges": [],
        },
        "budget_after_compact": 128,
    }


def _missing_pinned_patch() -> dict[str, JsonValue]:
    """构造不修改 pinned state 的 patch candidate。

    :returns: pinned patch JSON。
    """

    missing_field: dict[str, JsonValue] = {
        "operation": "missing",
        "value": None,
        "evidence_refs": [],
    }
    return {
        "candidate_id": "patch-missing",
        "current_goal": dict(missing_field),
        "confirmed_subjects": dict(missing_field),
        "user_constraints": dict(missing_field),
        "open_questions": dict(missing_field),
    }


def _fact_candidate(
    *,
    candidate_id: str = "fact-candidate-1",
    claim_text: str = "Canonical evidence supports revenue growth.",
    evidence_refs: tuple[str, ...] = ("evidence-1",),
) -> dict[str, JsonValue]:
    """构造 evidence-backed fact candidate JSON。

    :param candidate_id: candidate-local id。
    :param claim_text: fact claim 文本。
    :param evidence_refs: canonical evidence refs。
    :returns: fact candidate JSON。
    """

    return {
        "candidate_id": candidate_id,
        "claim_text": claim_text,
        "evidence_kind": EvidenceBackedFactKind.OBSERVED_VALUE.value,
        "evidence_refs": list(evidence_refs),
        "attributes": {"source": "test"},
    }


def _minimum_preserve_item(
    *,
    item_id: str = "minimum-item-1",
    label: str = "factor",
    text: str = "the second factor",
    source_refs: tuple[str, ...] = ("event-input",),
) -> dict[str, JsonValue]:
    """构造 minimum preserve item candidate JSON。

    :param item_id: item-local id。
    :param label: continuity label。
    :param text: continuity 文本。
    :param source_refs: 来源 refs。
    :returns: minimum preserve item candidate JSON。
    """

    return {
        "item_id": item_id,
        "label": label,
        "text": text,
        "source_refs": list(source_refs),
        "preserve_reason": MinimumPreserveReason.NEEDED_FOR_LOCAL_FOLLOWUP.value,
    }


def _append_memory_event(
    transaction: HostTransaction,
    *,
    event_id: str,
    event_type: str,
    payload: dict[str, JsonValue],
    event_class: EventClass = EventClass.CANONICAL_FACT,
) -> EventLogRow:
    """在 transaction 内追加 memory projection 测试 EventLog row。

    :param transaction: Host transaction。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: payload JSON。
    :param event_class: EventLog class。
    :returns: EventLog row。
    """

    return append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=event_class,
            session_id=_SESSION_ID,
            run_id="run-1",
            attempt_id="attempt-1",
            execution_id="execution-1",
            event_type=event_type,
            occurred_at=_OCCURRED_AT,
            actor="pytest",
            source="pytest",
            client_request_id=None,
            idempotency_key=None,
            policy_decision=None,
            reason=None,
            payload_json=payload,
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def _event_log_count(transaction: HostTransaction) -> int:
    """读取 EventLog row 数。

    :param transaction: Host transaction。
    :returns: EventLog row 数。
    :raises HostDurableError: count row 缺失或类型非法时抛出。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS count FROM {TABLE_EVENT_LOG}", ())
    if row is None:
        raise HostDurableError("event log count row missing")
    value = row.get("count")
    if not isinstance(value, int):
        raise HostDurableError("event log count must be int")
    return value


def _damage_latest_memory_snapshot(
    transaction: HostTransaction, *, policy_digest: str
) -> None:
    """破坏 latest memory snapshot JSON。

    :param transaction: Host transaction。
    :param policy_digest: memory policy digest。
    :returns: ``None``。
    """

    row = read_latest_memory_snapshot(
        transaction,
        session_id=_SESSION_ID,
        consumer_id=_CONSUMER_ID,
        policy_digest=policy_digest,
    )
    if row is None:
        raise HostDurableError("memory snapshot missing")
    transaction.execute(
        f"UPDATE {TABLE_HOST_MEMORY_SNAPSHOTS} SET snapshot_json = ? WHERE snapshot_id = ?",
        ('{"snapshot_id":"damaged"}', row.snapshot.snapshot_id),
    )


def _tool_provenance() -> MemoryProvenanceRef:
    """构造 compact HOST_PROJECTION provenance。

    :returns: compact provenance ref。
    """

    return MemoryProvenanceRef(
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name="host_projection",
        event_id="event-1",
        event_sequence=1,
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        tool_result_ref=None,
        payload_ref="payload-1",
        digest_ref="sha256:1111111111111111111111111111111111111111111111111111111111111111",
        source_refs=(),
    )


def _user_provenance() -> MemoryProvenanceRef:
    """构造 USER provenance。

    :returns: USER provenance ref。
    """

    return MemoryProvenanceRef(
        producer_kind=MemoryProducerKind.USER,
        producer_name="user",
        event_id="event-1",
        event_sequence=1,
        run_id="run-1",
        attempt_id=None,
        execution_id=None,
        tool_result_ref=None,
        payload_ref=None,
        digest_ref="sha256:2222222222222222222222222222222222222222222222222222222222222222",
        source_refs=(),
    )


def _working_assumption(
    *,
    item_id: str,
    assumption_summary: str,
    event_sequence: int,
) -> WorkingAssumptionView:
    """构造测试用 working assumption view。

    :param item_id: memory item id。
    :param assumption_summary: assumption 摘要。
    :param event_sequence: 来源 EventLog sequence。
    :returns: working assumption view。
    """

    return WorkingAssumptionView(
        item_id=item_id,
        assumption_summary=assumption_summary,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        producer_kind=MemoryProducerKind.ASSISTANT,
        event_id=f"event-assumption-{event_sequence}",
        event_sequence=event_sequence,
        run_id=f"run-assumption-{event_sequence}",
        subject_refs=(),
        included_reason=MemoryIncludedReason.WORKING_ASSUMPTION,
        excluded_reason=None,
        size_units=MemorySizeUnits(units=1),
    )


class _WriteSnapshotOperation:
    """写入 snapshot 的 transaction operation。

    :param snapshot_id: snapshot id。
    """

    def __init__(self, snapshot_id: str) -> None:
        """初始化 operation。

        :param snapshot_id: snapshot id。
        :returns: ``None``。
        """

        self._snapshot_id = snapshot_id
        self.policy_digest = digest_memory_projection_policy(_policy())

    def __call__(self, transaction: HostTransaction) -> MemorySnapshotRow:
        """写入空 memory snapshot 并确保 checkpoint。

        :param transaction: Host durable transaction。
        :returns: 写入后的 snapshot row。
        :raises HostDurableError: durable 写入失败时抛出。
        """

        snapshot = build_empty_conversation_memory_snapshot(
            snapshot_id=self._snapshot_id,
            session_id=_SESSION_ID,
            consumer_id=_CONSUMER_ID,
            policy_digest=self.policy_digest,
            built_at=_NOW,
        )
        return write_memory_snapshot_with_checkpoint(
            transaction,
            snapshot,
            now=_NOW,
        )


class _ReadLatestSnapshotOperation:
    """读取最新 snapshot 的 transaction operation。

    :param policy_digest: memory policy digest。
    """

    def __init__(self, policy_digest: str) -> None:
        """初始化 operation。

        :param policy_digest: memory policy digest。
        :returns: ``None``。
        """

        self._policy_digest = policy_digest

    def __call__(self, transaction: HostTransaction) -> MemorySnapshotRow | None:
        """读取最新 memory snapshot。

        :param transaction: Host durable transaction。
        :returns: snapshot row 或 ``None``。
        :raises HostDurableError: durable 读取失败时抛出。
        """

        return read_latest_memory_snapshot(
            transaction,
            session_id=_SESSION_ID,
            consumer_id=_CONSUMER_ID,
            policy_digest=self._policy_digest,
        )


class _ReadCheckpointOperation:
    """读取 projection checkpoint 的 transaction operation。"""

    def __call__(
        self, transaction: HostTransaction
    ) -> ProjectionCheckpointRow | None:
        """读取 memory consumer checkpoint。

        :param transaction: Host durable transaction。
        :returns: checkpoint row 或 ``None``。
        :raises HostDurableError: durable 读取失败时抛出。
        """

        return read_projection_checkpoint(transaction, _CONSUMER_ID)


class _ReadCheckpointForConsumerOperation:
    """按 consumer id 读取 projection checkpoint 的 transaction operation。

    :param consumer_id: projection consumer id。
    """

    def __init__(self, consumer_id: str) -> None:
        """初始化 operation。

        :param consumer_id: projection consumer id。
        :returns: ``None``。
        """

        self._consumer_id = consumer_id

    def __call__(
        self, transaction: HostTransaction
    ) -> ProjectionCheckpointRow | None:
        """读取目标 consumer checkpoint。

        :param transaction: Host transaction。
        :returns: checkpoint row 或 ``None``。
        :raises HostDurableError: durable 读取失败时抛出。
        """

        return read_projection_checkpoint(transaction, self._consumer_id)


class _ReadProjectionFailureOperation:
    """读取 projection failure 的 transaction operation。

    :param consumer_id: projection consumer id。
    """

    def __init__(self, consumer_id: str) -> None:
        """初始化 operation。

        :param consumer_id: projection consumer id。
        :returns: ``None``。
        """

        self._consumer_id = consumer_id

    def __call__(self, transaction: HostTransaction) -> ProjectionFailureRow | None:
        """读取 projection failure row。

        :param transaction: Host transaction。
        :returns: projection failure row 或 ``None``。
        :raises HostDurableError: durable 读取失败时抛出。
        """

        return read_projection_failure(transaction, self._consumer_id)


class _WriteThenFailOperation:
    """写入 snapshot 后抛错的 transaction operation。

    :param snapshot_id: snapshot id。
    """

    def __init__(self, snapshot_id: str) -> None:
        """初始化 operation。

        :param snapshot_id: snapshot id。
        :returns: ``None``。
        """

        self._write_operation = _WriteSnapshotOperation(snapshot_id)
        self.policy_digest = self._write_operation.policy_digest

    def __call__(self, transaction: HostTransaction) -> None:
        """写入 snapshot 后抛出结构化错误以验证 rollback。

        :param transaction: Host durable transaction。
        :returns: ``None``。
        :raises HostDurableError: 始终抛出以触发 rollback。
        """

        self._write_operation(transaction)
        raise HostDurableError("force rollback")


class _WriteDiagnosticOperation:
    """写入 diagnostic 的 transaction operation。

    :param diagnostic: memory diagnostic。
    """

    def __init__(self, diagnostic: MemoryDiagnostic) -> None:
        """初始化 operation。

        :param diagnostic: memory diagnostic。
        :returns: ``None``。
        """

        self._diagnostic = diagnostic

    def __call__(self, transaction: HostTransaction) -> MemoryDiagnosticRow:
        """写入 memory diagnostic。

        :param transaction: Host durable transaction。
        :returns: 写入后的 diagnostic row。
        :raises HostDurableError: durable 写入失败时抛出。
        """

        return write_memory_diagnostic(
            transaction,
            session_id=_SESSION_ID,
            snapshot_id=None,
            diagnostic=self._diagnostic,
            recorded_at=_NOW,
        )


class _ReadDiagnosticOperation:
    """读取 diagnostic 的 transaction operation。

    :param diagnostic_id: diagnostic id。
    """

    def __init__(self, diagnostic_id: str) -> None:
        """初始化 operation。

        :param diagnostic_id: diagnostic id。
        :returns: ``None``。
        """

        self._diagnostic_id = diagnostic_id

    def __call__(self, transaction: HostTransaction) -> MemoryDiagnosticRow | None:
        """读取 memory diagnostic。

        :param transaction: Host durable transaction。
        :returns: diagnostic row 或 ``None``。
        :raises HostDurableError: durable 读取失败时抛出。
        """

        return read_memory_diagnostic(transaction, self._diagnostic_id)


class _ForceOldVerifiedFactItemKindOperation:
    """强制写入旧 verified_fact item kind 的测试 operation。

    :param snapshot_id: snapshot id。
    """

    def __init__(self, snapshot_id: str) -> None:
        """初始化 operation。

        :param snapshot_id: snapshot id。
        :returns: ``None``。
        """

        self._snapshot_id = snapshot_id

    def __call__(self, transaction: HostTransaction) -> None:
        """临时关闭 CHECK 约束以模拟旧 durable row。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute("PRAGMA ignore_check_constraints = ON", ())
        try:
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_MEMORY_ITEMS}
                SET item_kind = ?
                WHERE snapshot_id = ?
                  AND item_kind = ?
                """,
                (
                    "verified_fact",
                    self._snapshot_id,
                    "evidence_backed_fact",
                ),
            )
        finally:
            transaction.execute("PRAGMA ignore_check_constraints = OFF", ())


def test_empty_event_log_snapshot_can_be_created_and_read(
    tmp_path: Path,
) -> None:
    """空 EventLog 下可以创建并读取空 memory snapshot。"""

    operation = _WriteSnapshotOperation("snapshot-empty")
    with open_host_durable_store(_options(tmp_path)) as store:
        written = store.transaction_runner.run_write(operation)
        read_back = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(operation.policy_digest)
        )
        checkpoint = store.transaction_runner.run_read(_ReadCheckpointOperation())

        assert written.snapshot.snapshot_id == "snapshot-empty"
        assert read_back is not None
        assert read_back.snapshot.evidence_backed_facts == ()
        assert read_back.snapshot.working_assumptions == ()
        assert read_back.snapshot.conversation_continuity.items == ()
        assert read_back.snapshot.cursor.checkpoint_event_sequence == 0
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 0


def test_snapshot_and_checkpoint_rollback_together(tmp_path: Path) -> None:
    """snapshot 与 checkpoint 在同一 transaction 内提交或一起 rollback。"""

    operation = _WriteThenFailOperation("snapshot-rollback")
    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(operation)
        read_back = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(operation.policy_digest)
        )
        checkpoint = store.transaction_runner.run_read(_ReadCheckpointOperation())

        assert read_back is None
        assert checkpoint is None


def test_typed_contracts_reject_invalid_ids_cursor_and_evidence_fact() -> None:
    """typed contracts 拒绝空 id、非法 cursor 与非法 evidence-backed fact。"""

    with pytest.raises(ValueError):
        OpaqueMemoryRef(ref_kind=HostNeutralRefKind.SUBJECT, ref_id="")
    with pytest.raises(ValueError):
        MemorySnapshotCursor(
            consumer_id=_CONSUMER_ID,
            checkpoint_event_sequence=0,
            checkpoint_event_id="event-1",
            session_id=_SESSION_ID,
        )
    with pytest.raises(ValueError):
        MemorySnapshotCursor(
            consumer_id=_CONSUMER_ID,
            checkpoint_event_sequence=1,
            checkpoint_event_id=None,
            session_id=_SESSION_ID,
        )
    with pytest.raises(ValueError):
        EvidenceBackedFactView(
            item_id="fact-1",
            claim_text="summary",
            evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
            evidence_refs=(),
            attributes={},
            provenance=_tool_provenance(),
            extraction_operation_ref="event:event-1",
            compact_artifact_ref=None,
            candidate_id="candidate-1",
            included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
            excluded_reason=None,
            size_units=MemorySizeUnits(units=7),
        )
    with pytest.raises(ValueError):
        EvidenceBackedFactView(
            item_id="fact-1",
            claim_text="summary",
            evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
            evidence_refs=("evidence-1",),
            attributes={},
            provenance=_user_provenance(),
            extraction_operation_ref="event:event-1",
            compact_artifact_ref=None,
            candidate_id="candidate-1",
            included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
            excluded_reason=None,
            size_units=MemorySizeUnits(units=7),
        )
    with pytest.raises(ValueError, match="claim_text"):
        EvidenceBackedFactView(
            item_id="fact-1",
            claim_text="x" * (MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS + 1),
            evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
            evidence_refs=("evidence-1",),
            attributes={},
            provenance=_tool_provenance(),
            extraction_operation_ref="event:event-1",
            compact_artifact_ref=None,
            candidate_id="candidate-1",
            included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
            excluded_reason=None,
            size_units=MemorySizeUnits(units=7),
        )


def test_pinned_state_open_questions_are_not_duplicated() -> None:
    """PinnedStateView 拥有 open_questions 且不在 working assumption 中重复建模。"""

    view = PinnedStateView(
        current_goal="goal",
        confirmed_subjects=(),
        user_constraints=("constraint",),
        open_questions=("question",),
    )

    assert view.current_goal == "goal"
    assert view.open_questions == ("question",)
    assert "open_questions" not in {
        field.name for field in fields(WorkingAssumptionView)
    }

    normalized_duplicate = PinnedStateView(
        current_goal=None,
        confirmed_subjects=(),
        user_constraints=(),
        open_questions=("Question", "  question  "),
    )
    assert normalized_duplicate.open_questions == ("  question  ",)


def test_working_assumptions_deduplicate_normalized_summary_before_limit() -> None:
    """Working assumptions 先按 normalized summary 去重，再进入预算裁剪。"""

    policy = replace(_policy(), max_working_assumptions=2)
    policy_digest = digest_memory_projection_policy(policy)
    base = build_empty_conversation_memory_snapshot(
        snapshot_id="memory-snapshot-working-assumptions",
        session_id=_SESSION_ID,
        consumer_id=_CONSUMER_ID,
        policy_digest=policy_digest,
        built_at=_NOW,
    )
    previous = replace(
        base,
        cursor=MemorySnapshotCursor(
            consumer_id=_CONSUMER_ID,
            checkpoint_event_sequence=3,
            checkpoint_event_id="event-assumption-3",
            session_id=_SESSION_ID,
        ),
        working_assumptions=(
            _working_assumption(
                item_id="assumption-cash",
                assumption_summary="cash runway needs verification",
                event_sequence=1,
            ),
            _working_assumption(
                item_id="assumption-margin-old",
                assumption_summary="Verify margin bridge",
                event_sequence=2,
            ),
            _working_assumption(
                item_id="assumption-margin-new",
                assumption_summary="  verify   MARGIN bridge  ",
                event_sequence=3,
            ),
        ),
    )

    snapshot = project_conversation_memory_event(
        previous_snapshot=previous,
        event=_memory_event(
            event_sequence=4,
            event_id="event-user-after-assumptions",
            event_type="USER_INPUT_ACCEPTED",
            payload={"display_text": "continue analysis"},
            attempt_id=None,
            execution_id=None,
        ),
        policy=policy,
        built_at=_NOW,
        consumer_id=_CONSUMER_ID,
    )

    assert tuple(
        (item.item_id, item.assumption_summary)
        for item in snapshot.working_assumptions
    ) == (
        ("assumption-cash", "cash runway needs verification"),
        ("assumption-margin-new", "  verify   MARGIN bridge  "),
    )


def test_open_questions_deduplicate_normalized_text_before_pinned_limit() -> None:
    """Open questions 先按 normalized text 去重，再进入 pinned 数量裁剪。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-open-question-dedup",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="open question dedup summary",
                    pinned_patch={
                        "candidate_id": "patch-open-question-dedup",
                        "current_goal": {
                            "operation": "missing",
                            "value": None,
                            "evidence_refs": [],
                        },
                        "confirmed_subjects": {
                            "operation": "missing",
                            "value": None,
                            "evidence_refs": [],
                        },
                        "user_constraints": {
                            "operation": "missing",
                            "value": None,
                            "evidence_refs": [],
                        },
                        "open_questions": {
                            "operation": "replace",
                            "value": [
                                "what are the covenants?",
                                "Verify margin bridge",
                                "  verify   MARGIN bridge  ",
                            ],
                            "evidence_refs": ["evidence-1"],
                        },
                    },
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        ),
        policy=replace(_policy(), max_pinned_items=2),
    )

    assert snapshot.pinned_state.open_questions == (
        "what are the covenants?",
        "  verify   MARGIN bridge  ",
    )


def test_host_neutral_ref_kind_rejects_business_specific_kind() -> None:
    """OpaqueMemoryRef.ref_kind 只接受 Host-neutral enum 值。"""

    with pytest.raises(ValueError):
        OpaqueMemoryRef(
            ref_kind=cast(HostNeutralRefKind, "company"),
            ref_id="opaque-company-ref",
        )
    assert {kind.value for kind in HostNeutralRefKind} == {
        "source",
        "chunk",
        "entity",
        "subject",
        "topic",
        "evidence",
        "payload",
        "external",
    }


def test_memory_contracts_do_not_expose_business_specific_fields() -> None:
    """Host memory contracts 不包含业务专有字段。"""

    contract_names = {
        name
        for contract in (
            OpaqueMemoryRef,
            MemoryProvenanceRef,
            PinnedStateView,
            EvidenceBackedFactView,
            WorkingAssumptionView,
            ConversationContinuityItem,
            MemoryDiagnostic,
        )
        for name in (field.name for field in fields(contract))
    }
    enum_values = {
        value
        for enum_values in (
            (kind.value for kind in HostNeutralRefKind),
            (status.value for status in MemoryClaimStatus),
        )
        for value in enum_values
    }
    searchable = " ".join(sorted(contract_names | enum_values))

    assert all(term not in searchable for term in _FORBIDDEN_BUSINESS_TERMS)


def test_memory_diagnostic_contract_round_trips_through_durable_store(
    tmp_path: Path,
) -> None:
    """MemoryDiagnostic 使用 memory diagnostics table 持久化。"""

    policy_digest = digest_memory_projection_policy(_policy())
    diagnostic = MemoryDiagnostic(
        diagnostic_id="diagnostic-1",
        reason=MemoryDiagnosticReason.EMPTY_EVENT_LOG_SNAPSHOT,
        message="empty event log snapshot created",
        event_sequence=None,
        item_id=None,
        policy_digest=policy_digest,
        recorded_at=_NOW,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        written = store.transaction_runner.run_write(
            _WriteDiagnosticOperation(diagnostic)
        )
        read_back = store.transaction_runner.run_read(
            _ReadDiagnosticOperation("diagnostic-1")
        )

        assert (
            written.diagnostic.reason
            is MemoryDiagnosticReason.EMPTY_EVENT_LOG_SNAPSHOT
        )
        assert read_back is not None
        assert read_back.diagnostic.policy_digest == policy_digest
        assert read_back.session_id == _SESSION_ID


def test_snapshot_digest_ignores_nondeterministic_diagnostic_fields() -> None:
    """snapshot digest 不受 diagnostic_id 与 recorded_at 影响。"""

    policy_digest = digest_memory_projection_policy(_policy())
    first = ConversationMemorySnapshot(
        snapshot_id="snapshot-1",
        session_id=_SESSION_ID,
        cursor=MemorySnapshotCursor(
            consumer_id=_CONSUMER_ID,
            checkpoint_event_sequence=0,
            checkpoint_event_id=None,
            session_id=_SESSION_ID,
        ),
        policy_digest=policy_digest,
        pinned_state=PinnedStateView(
            current_goal="goal",
            confirmed_subjects=(),
            user_constraints=("constraint",),
            open_questions=("question",),
        ),
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=ConversationContinuityView(items=()),
        diagnostics=(
            MemoryDiagnostic(
                diagnostic_id="diagnostic-a",
                reason=MemoryDiagnosticReason.BUDGET_LIMIT_REACHED,
                message="stable diagnostic semantic",
                event_sequence=1,
                item_id="item-1",
                policy_digest=policy_digest,
                recorded_at="2026-05-16T00:00:00.000000Z",
            ),
        ),
        built_at="2026-05-16T00:00:00.000000Z",
        snapshot_digest="pending",
    )
    second = ConversationMemorySnapshot(
        snapshot_id="snapshot-2",
        session_id=_SESSION_ID,
        cursor=first.cursor,
        policy_digest=policy_digest,
        pinned_state=first.pinned_state,
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=first.conversation_continuity,
        diagnostics=(
            MemoryDiagnostic(
                diagnostic_id="diagnostic-b",
                reason=MemoryDiagnosticReason.BUDGET_LIMIT_REACHED,
                message="stable diagnostic semantic",
                event_sequence=1,
                item_id="item-1",
                policy_digest=policy_digest,
                recorded_at="2026-05-17T00:00:00.000000Z",
            ),
        ),
        built_at="2026-05-17T00:00:00.000000Z",
        snapshot_digest="pending",
    )

    assert calculate_memory_snapshot_digest(first) == calculate_memory_snapshot_digest(
        second
    )


def test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded() -> None:
    """P9 typed view 主动投影只接受工具确认事实与 assumption。"""

    reserved_statuses = (
        MemoryClaimStatus.CONFLICTED,
        MemoryClaimStatus.STALE,
        MemoryClaimStatus.SUPERSEDED,
    )
    for status in reserved_statuses:
        with pytest.raises(ValueError):
            WorkingAssumptionView(
                item_id=f"assumption-{status.value}",
                assumption_summary="summary",
                claim_status=status,
                producer_kind=MemoryProducerKind.USER,
                event_id="event-1",
                event_sequence=1,
                run_id="run-1",
                subject_refs=(),
                included_reason=MemoryIncludedReason.WORKING_ASSUMPTION,
                excluded_reason=None,
                size_units=estimate_memory_size_units("summary"),
            )
        with pytest.raises(ValueError):
            ConversationContinuityItem(
                item_id=f"continuity-{status.value}",
                item_kind=ConversationContinuityKind.ASSISTANT_CONCLUSION,
                producer_kind=MemoryProducerKind.ASSISTANT,
                claim_status=status,
                event_id="event-1",
                event_sequence=1,
                run_id="run-1",
                summary_text="summary",
                label=None,
                source_refs=(),
                preserve_reason=None,
                payload_ref=None,
                payload_digest=None,
                included_reason=None,
                excluded_reason=MemoryExcludedReason.POLICY_EXCLUDED,
                size_units=estimate_memory_size_units("summary"),
            )


def test_final_answer_enters_continuity_not_evidence_fact() -> None:
    """RUN_SUCCEEDED final_answer 只进入 continuity，不进入 evidence-backed facts。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-final",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "assistant conclusion"},
                run_id="run-final",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert len(snapshot.conversation_continuity.items) == 1
    item = snapshot.conversation_continuity.items[0]
    assert item.item_kind is ConversationContinuityKind.ASSISTANT_CONCLUSION
    assert item.producer_kind is MemoryProducerKind.ASSISTANT
    assert item.claim_status is MemoryClaimStatus.ASSUMPTION
    assert item.summary_text == "assistant conclusion"


def test_user_input_never_enters_evidence_backed_facts() -> None:
    """USER_INPUT_ACCEPTED 可进入 pinned / continuity，但不得成为 evidence fact。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-user",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "use fiscal year 2025"},
                run_id="run-user",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert snapshot.pinned_state.user_constraints == ("use fiscal year 2025",)
    assert len(snapshot.conversation_continuity.items) == 1
    assert (
        snapshot.conversation_continuity.items[0].item_kind
        is ConversationContinuityKind.RAW_USER_TURN
    )
    assert (
        snapshot.conversation_continuity.items[0].producer_kind
        is MemoryProducerKind.USER
    )


def test_final_answer_user_input_summary_do_not_become_evidence_backed_fact() -> None:
    """final answer、user input 与 episode summary 都不得升级为 stable fact。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-user-claim-like",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "revenue was 100 according to me"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-final-answer-claim-like",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "assistant says revenue was 100"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-summary-claim-like",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="summary says revenue was 100"),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert any(
        item.item_kind is ConversationContinuityKind.ASSISTANT_CONCLUSION
        and item.summary_text == "assistant says revenue was 100"
        for item in snapshot.conversation_continuity.items
    )
    assert any(
        item.item_kind is ConversationContinuityKind.EPISODE_SUMMARY
        and item.summary_text == "summary says revenue was 100"
        for item in snapshot.conversation_continuity.items
    )


def test_current_goal_first_write_wins_and_later_inputs_are_constraints() -> None:
    """多次 USER_INPUT_ACCEPTED 只把第一条写入 current_goal。

    :returns: ``None``。
    :raises AssertionError: first-write-wins 或后续约束投影不符合预期时抛出。
    """

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-user-first-goal",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "first accepted goal"},
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-user-second-constraint",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "second accepted constraint"},
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-user-third-constraint",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "third accepted constraint"},
            ),
        )
    )

    assert snapshot.pinned_state.current_goal == "first accepted goal"
    assert snapshot.pinned_state.user_constraints == (
        "first accepted goal",
        "second accepted constraint",
        "third accepted constraint",
    )


def test_current_goal_preserved_when_projecting_later_user_delta() -> None:
    """已有 current_goal 的 snapshot 投影后续用户输入时保留原目标。

    :returns: ``None``。
    :raises AssertionError: 后续 delta 覆盖既有 current_goal 时抛出。
    """

    base = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-user-existing-goal",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "existing goal"},
            ),
        )
    )

    repaired = project_conversation_memory_event(
        previous_snapshot=base,
        event=_memory_event(
            event_sequence=2,
            event_id="event-user-inline-delta",
            event_type="USER_INPUT_ACCEPTED",
            payload={"display_text": "newer inline delta prompt"},
        ),
        policy=_policy(),
        built_at=_NOW,
        consumer_id=_CONSUMER_ID,
    )

    assert repaired.pinned_state.current_goal == "existing goal"
    assert repaired.pinned_state.user_constraints == (
        "existing goal",
        "newer inline delta prompt",
    )


def test_tool_result_accepted_does_not_project_evidence_backed_fact() -> None:
    """TOOL_RESULT_ACCEPTED 只推进 cursor，不直接生成 evidence-backed fact。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=2,
                event_id="event-tool-result",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=_tool_payload(summary="tool supplied neutral summary"),
                run_id="run-1",
                attempt_id="attempt-1",
                execution_id="execution-1",
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert snapshot.diagnostics == ()
    assert snapshot.cursor.checkpoint_event_id == "event-tool-result"


def test_missing_tool_fact_summary_does_not_use_neutral_fallback() -> None:
    """缺失工具 fact summary 时不生成 fallback fact 或 diagnostic。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=3,
                event_id="event-tool-missing-summary",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=_tool_payload(summary=None),
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert snapshot.diagnostics == ()


def test_missing_tool_name_does_not_project_unknown_tool_producer() -> None:
    """缺失 tool_name 时也不从 TOOL_RESULT_ACCEPTED 生成 producer fact。"""

    payload = _tool_payload(summary=None)
    del payload["tool_name"]
    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=3,
                event_id="event-tool-missing-name",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=payload,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert snapshot.diagnostics == ()


def test_invalid_source_refs_do_not_create_tool_result_fact() -> None:
    """Malformed source_refs 不应导致 TOOL_RESULT_ACCEPTED 生成 fact。"""

    payload = _tool_payload(summary="summary with malformed refs")
    payload["source_refs"] = [
        {"ref_kind": "invalid-kind", "ref_id": "bad-ref"},
        {"ref_kind": HostNeutralRefKind.SOURCE.value, "ref_id": "good-ref"},
    ]
    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=3,
                event_id="event-tool-bad-source-ref",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=payload,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert snapshot.diagnostics == ()


def test_projection_ignores_reserved_claim_status_from_payload() -> None:
    """P9 projection 不从 payload 主动合成 reserved claim statuses。"""

    payload = _tool_payload(summary="tool supplied neutral summary")
    payload["claim_status"] = MemoryClaimStatus.CONFLICTED.value
    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=4,
                event_id="event-tool-reserved-status",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=payload,
            ),
        )
    )

    statuses = {
        item.claim_status
        for item in snapshot.working_assumptions
    } | {
        item.claim_status
        for item in snapshot.conversation_continuity.items
    }
    assert MemoryClaimStatus.CONFLICTED not in statuses
    assert MemoryClaimStatus.STALE not in statuses
    assert MemoryClaimStatus.SUPERSEDED not in statuses
    assert statuses == set()


def test_episode_summary_does_not_replace_evidence_anchor() -> None:
    """Episode summary 只是 continuity navigation，不从 tool result 补 fact。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-tool-with-evidence",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=_tool_payload(summary="tool supplied neutral summary"),
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-episode",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="navigation only"),
                run_id=None,
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert len(snapshot.conversation_continuity.items) == 1
    assert (
        snapshot.conversation_continuity.items[0].item_kind
        is ConversationContinuityKind.EPISODE_SUMMARY
    )


def test_context_compacted_episode_summary_becomes_assumption_continuity() -> None:
    """accepted compact summary 只成为 assumption continuity item。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-summary",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="accepted compact summary"),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert len(snapshot.conversation_continuity.items) == 1
    item = snapshot.conversation_continuity.items[0]
    assert item.item_kind is ConversationContinuityKind.EPISODE_SUMMARY
    assert item.claim_status is MemoryClaimStatus.ASSUMPTION
    assert item.producer_kind is MemoryProducerKind.HOST_PROJECTION
    assert item.summary_text == "accepted compact summary"


def test_context_compacted_fact_candidates_materialize_evidence_backed_facts() -> None:
    """accepted compact fact candidates 物化 claim_text 与 evidence_refs。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-fact",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary with accepted fact",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="candidate-local-only",
                            claim_text="Revenue increased based on canonical evidence.",
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert len(snapshot.evidence_backed_facts) == 1
    fact = snapshot.evidence_backed_facts[0]
    assert fact.claim_text == "Revenue increased based on canonical evidence."
    assert fact.evidence_refs == ("evidence-1",)
    assert fact.evidence_kind is EvidenceBackedFactKind.OBSERVED_VALUE
    assert fact.provenance.event_id == "event-compact-fact"
    assert fact.provenance.event_sequence == 1
    assert fact.provenance.producer_kind is MemoryProducerKind.HOST_PROJECTION
    assert fact.candidate_id == "candidate-local-only"
    assert fact.candidate_id != fact.provenance.event_id


def test_context_compacted_summary_can_reference_same_event_materialized_fact() -> None:
    """compact summary fact refs 可覆盖同一 compact event 物化的新 facts。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-summary-fact-coverage",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary cites compact materialized fact",
                    confirmed_fact_refs=("fact-candidate-coverage",),
                    fact_candidates=[
                        _fact_candidate(candidate_id="fact-candidate-coverage")
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert len(snapshot.evidence_backed_facts) == 1
    assert snapshot.conversation_continuity.items[0].summary_text == (
        "summary cites compact materialized fact"
    )


def test_compaction_confirmed_facts_do_not_drift_or_create_summary_fact() -> None:
    """summary 引用 facts / evidence 时不得改写 facts 或自行建 fact。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-gross-margin-facts",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text=(
                        "summary references revenue and gross profit facts"
                    ),
                    confirmed_fact_refs=("fact-revenue", "fact-gross-profit"),
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="fact-revenue",
                            claim_text="Revenue was 100.",
                        ),
                        _fact_candidate(
                            candidate_id="fact-gross-profit",
                            claim_text="Gross profit was 40.",
                        ),
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert tuple(fact.candidate_id for fact in snapshot.evidence_backed_facts) == (
        "fact-revenue",
        "fact-gross-profit",
    )
    assert tuple(fact.claim_text for fact in snapshot.evidence_backed_facts) == (
        "Revenue was 100.",
        "Gross profit was 40.",
    )
    assert tuple(fact.evidence_refs for fact in snapshot.evidence_backed_facts) == (
        ("evidence-1",),
        ("evidence-1",),
    )
    assert len(snapshot.evidence_backed_facts) == 2
    assert len(snapshot.conversation_continuity.items) == 1
    summary = snapshot.conversation_continuity.items[0]
    assert summary.item_kind is ConversationContinuityKind.EPISODE_SUMMARY
    assert summary.claim_status is MemoryClaimStatus.ASSUMPTION
    assert summary.summary_text == "summary references revenue and gross profit facts"


def test_evidence_backed_fact_budget_keeps_latest_facts_and_records_diagnostic() -> None:
    """max_evidence_backed_facts 保留最新 facts 并记录 budget diagnostic。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-fact-1",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary one",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="fact-oldest",
                            claim_text="oldest fact",
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-fact-2",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary two",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="fact-kept-one",
                            claim_text="kept fact one",
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-compact-fact-3",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary three",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="fact-kept-two",
                            claim_text="kept fact two",
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        ),
        policy=_small_fact_budget_policy(),
    )

    assert tuple(fact.claim_text for fact in snapshot.evidence_backed_facts) == (
        "kept fact one",
        "kept fact two",
    )
    assert any(
        diagnostic.reason is MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
        and diagnostic.message == "evidence-backed facts limited by memory policy"
        for diagnostic in snapshot.diagnostics
    )


def test_memory_projection_materializes_pinned_state_current_value_not_patch_log() -> None:
    """compact 后 pinned state 只暴露当前物化值，不保留 patch log。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-goal-one",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="first goal compact",
                    pinned_patch={
                        "candidate_id": "patch-goal-one",
                        "current_goal": {
                            "operation": "replace",
                            "value": "analyze revenue",
                            "evidence_refs": ["evidence-1"],
                        },
                    },
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-goal-two",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="second goal compact",
                    pinned_patch={
                        "candidate_id": "patch-goal-two",
                        "current_goal": {
                            "operation": "replace",
                            "value": "analyze margin",
                            "evidence_refs": ["evidence-1"],
                        },
                    },
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.pinned_state.current_goal == "analyze margin"
    assert snapshot.pinned_state.user_constraints == ()
    assert all("analyze revenue" != item for item in snapshot.pinned_state.open_questions)


def test_evidence_backed_fact_working_set_is_bounded_and_deterministic() -> None:
    """fact working set 按 dedupe key 去重，并只保留 policy bounded 集合。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-duplicate-old",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="old duplicate",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="fact-duplicate-old",
                            claim_text="Revenue   was 100.",
                            evidence_refs=("evidence-2", "evidence-1"),
                        )
                    ],
                    canonical_evidence_refs=("evidence-1", "evidence-2"),
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-duplicate-new",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="new duplicate",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="fact-duplicate-new",
                            claim_text=" revenue was 100. ",
                            evidence_refs=("evidence-1", "evidence-2"),
                        )
                    ],
                    canonical_evidence_refs=("evidence-1", "evidence-2"),
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-compact-second-fact",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="second fact",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="fact-second",
                            claim_text="Gross profit was 40.",
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        ),
        policy=_small_fact_budget_policy(),
    )

    assert tuple(fact.candidate_id for fact in snapshot.evidence_backed_facts) == (
        "fact-duplicate-new",
        "fact-second",
    )
    assert tuple(
        fact.provenance.event_sequence for fact in snapshot.evidence_backed_facts
    ) == (2, 3)
    assert any(
        diagnostic.reason is MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_SUPERSEDED
        and diagnostic.item_id is not None
        and "fact-duplicate-old" in diagnostic.item_id
        for diagnostic in snapshot.diagnostics
    )


def test_episode_summaries_are_policy_bounded_not_append_only_rendered() -> None:
    """episode summaries 只保留 policy bounded recent working set。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-summary-one",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="summary one"),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-summary-two",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="summary two"),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-compact-summary-three",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="summary three"),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=4,
                event_id="event-compact-summary-four",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="summary four"),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    summaries = tuple(
        item.summary_text
        for item in snapshot.conversation_continuity.items
        if item.item_kind is ConversationContinuityKind.EPISODE_SUMMARY
    )
    assert summaries == ("summary three", "summary four")
    assert any(
        diagnostic.reason is MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
        for diagnostic in snapshot.diagnostics
    )


def test_minimum_preserve_expires_when_covered_by_stable_or_summary() -> None:
    """minimum preserve 被后续 summary 覆盖后退出 continuity working set。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-preserve-before-summary",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="preserve producer",
                    minimum_preserve_items=[
                        _minimum_preserve_item(
                            item_id="covered-preserve",
                            source_refs=("event-input",),
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-covering-summary",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="covering summary"),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert all(
        item.item_kind is not ConversationContinuityKind.MINIMUM_PRESERVE_ITEM
        for item in snapshot.conversation_continuity.items
    )
    assert any(
        diagnostic.reason is MemoryDiagnosticReason.MINIMUM_PRESERVE_ITEM_COVERED
        for diagnostic in snapshot.diagnostics
    )


def test_context_compacted_invalid_fact_candidates_record_diagnostic_only() -> None:
    """invalid fact candidates 只产生 diagnostic，不合成 fallback fact。"""

    payload = _compact_payload(
        summary_text="summary with invalid fact candidate",
        fact_candidates=[
            _fact_candidate(
                claim_text="Invalid evidence ref candidate.",
                evidence_refs=("missing-evidence",),
            )
        ],
    )
    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-invalid-fact",
                event_type="CONTEXT_COMPACTED",
                payload=payload,
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert any(
        diagnostic.reason
        is MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID
        for diagnostic in snapshot.diagnostics
    )


def test_invalid_fact_candidate_diagnostic_survives_durable_snapshot_write(
    tmp_path: Path,
) -> None:
    """invalid fact candidate diagnostic 可通过 durable CHECK 并持久化。"""

    policy = _policy()
    consumer = ConversationMemoryProjectionConsumer(policy)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-compact-invalid-durable-fact",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary with invalid durable fact candidate",
                    fact_candidates=[
                        _fact_candidate(
                            claim_text="Invalid durable evidence ref candidate.",
                            evidence_refs=("missing-evidence",),
                        )
                    ],
                ),
            )
        )

        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId(CONVERSATION_MEMORY_CONSUMER_ID),
            limit=10,
        )
        read_back = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(policy))
        )

        assert result.events_applied == 1
        assert read_back is not None
        assert read_back.snapshot.evidence_backed_facts == ()
        assert any(
            diagnostic.reason
            is MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID
            for diagnostic in read_back.snapshot.diagnostics
        )


def test_fact_candidate_error_does_not_mask_non_fact_candidate_error() -> None:
    """fact candidate 错误不得掩盖 minimum preserve 等非 fact 字段错误。"""

    payload = _compact_payload(
        summary_text="summary with multiple invalid candidate fields",
        fact_candidates=[
            _fact_candidate(
                claim_text="Invalid evidence ref candidate.",
                evidence_refs=("missing-evidence",),
            )
        ],
        minimum_preserve_items=[
            _minimum_preserve_item(
                text="x" * (MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS + 1)
            )
        ],
    )

    with pytest.raises(
        ValueError,
        match="minimum preserve text exceeds maximum length",
    ):
        _build_snapshot(
            (
                _memory_event(
                    event_sequence=1,
                    event_id="event-compact-invalid-non-fact",
                    event_type="CONTEXT_COMPACTED",
                    payload=payload,
                    run_id="run-compact",
                    attempt_id=None,
                    execution_id=None,
                ),
            )
        )


def test_overlong_fact_candidate_records_diagnostic_without_fact() -> None:
    """超长 claim_text 只记录 diagnostic，不进入 stable facts。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-overlong-fact",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary with overlong fact",
                    fact_candidates=[
                        _fact_candidate(
                            claim_text=(
                                "x"
                                * (MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS + 1)
                            )
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert any(
        diagnostic.reason
        is MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID
        for diagnostic in snapshot.diagnostics
    )


def test_context_compacted_missing_fact_candidates_record_diagnostic_only() -> None:
    """缺失 fact candidate 字段只产生 diagnostic，不回退生成 fact。"""

    payload = _compact_payload(summary_text="summary without fact candidate field")
    del payload["evidence_backed_fact_candidates"]
    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-missing-fact-candidates",
                event_type="CONTEXT_COMPACTED",
                payload=payload,
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert any(
        diagnostic.reason
        is MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID
        for diagnostic in snapshot.diagnostics
    )


def test_minimum_preserve_candidates_create_continuity_items_only() -> None:
    """minimum preserve candidates 只物化 continuity，不产生 facts。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-minimum-preserve",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary with minimum preserve",
                    minimum_preserve_items=[
                        _minimum_preserve_item(
                            label="second factor",
                            text="Keep reference to the second factor.",
                        )
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    preserve_items = tuple(
        item
        for item in snapshot.conversation_continuity.items
        if item.item_kind is ConversationContinuityKind.MINIMUM_PRESERVE_ITEM
    )
    assert len(preserve_items) == 1
    assert preserve_items[0].summary_text == "Keep reference to the second factor."
    assert preserve_items[0].label == "second factor"
    assert preserve_items[0].source_refs == ("event-input",)
    assert (
        preserve_items[0].preserve_reason
        is MinimumPreserveReason.NEEDED_FOR_LOCAL_FOLLOWUP
    )


def test_context_compacted_pinned_patch_updates_clears_and_preserves() -> None:
    """accepted pinned patch 按字段三态更新、清空或保留字段。"""

    first = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-initial-user",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "existing goal"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-patch",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="patch summary",
                    pinned_patch={
                        "candidate_id": "patch-tristate",
                        "current_goal": {
                            "operation": "replace",
                            "value": "replacement goal",
                            "evidence_refs": ["evidence-1"],
                        },
                        "confirmed_subjects": {
                            "operation": "replace",
                            "value": [
                                {
                                    "ref_kind": "subject",
                                    "ref_id": "issuer-a",
                                }
                            ],
                            "evidence_refs": ["evidence-1"],
                        },
                        "user_constraints": {
                            "operation": "clear",
                            "value": None,
                            "evidence_refs": ["evidence-1"],
                        },
                    },
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert first.pinned_state.current_goal == "replacement goal"
    assert first.pinned_state.user_constraints == ()
    assert first.pinned_state.open_questions == ()
    assert first.pinned_state.confirmed_subjects == (
        OpaqueMemoryRef(
            ref_kind=HostNeutralRefKind.SUBJECT,
            ref_id="issuer-a",
            digest=None,
        ),
    )

    second = project_conversation_memory_event(
        previous_snapshot=first,
        event=_memory_event(
            event_sequence=3,
            event_id="event-compact-preserve",
            event_type="CONTEXT_COMPACTED",
            payload=_compact_payload(
                summary_text="preserve summary",
                pinned_patch={
                    "candidate_id": "patch-preserve",
                    "open_questions": {
                        "operation": "replace",
                        "value": ["verify margin"],
                        "evidence_refs": ["evidence-1"],
                    },
                },
            ),
            run_id="run-compact",
            attempt_id=None,
            execution_id=None,
        ),
        policy=_policy(),
        built_at=_NOW,
        consumer_id=_CONSUMER_ID,
    )

    assert second.pinned_state.current_goal == "replacement goal"
    assert second.pinned_state.confirmed_subjects == first.pinned_state.confirmed_subjects
    assert second.pinned_state.user_constraints == ()
    assert second.pinned_state.open_questions == ("verify margin",)


def test_context_compacted_rejects_free_form_confirmed_subject_patch() -> None:
    """confirmed_subjects patch 只能使用 Host-neutral opaque refs。"""

    with pytest.raises(ValueError, match="opaque ref text requires kind prefix"):
        _build_snapshot(
            (
                _memory_event(
                    event_sequence=1,
                    event_id="event-compact-bad-subject",
                    event_type="CONTEXT_COMPACTED",
                    payload=_compact_payload(
                        summary_text="bad subject",
                        pinned_patch={
                            "candidate_id": "patch-bad-subject",
                            "confirmed_subjects": {
                                "operation": "replace",
                                "value": ["Apple Inc."],
                                "evidence_refs": ["evidence-1"],
                            },
                        },
                    ),
                ),
            )
        )


def test_context_compacted_summary_fact_refs_do_not_create_evidence_backed_facts() -> None:
    """summary fact refs 不会让 TOOL_RESULT_ACCEPTED 直接生成 fact。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-tool-for-summary",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=_tool_payload(summary="tool supplied neutral summary"),
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-with-fact-ref",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary cites tool fact",
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert len(snapshot.conversation_continuity.items) == 1
    assert snapshot.conversation_continuity.items[0].summary_text == (
        "summary cites tool fact"
    )


def test_history_pool_preserves_recent_floor_and_drops_summaries_first() -> None:
    """低预算下 recent raw turn floor 保留，summary 先于 older raw turn 被丢弃。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-old-user",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "old"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-episode",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="episode-summary"),
                run_id=None,
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-recent-user-1",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "r1"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=4,
                event_id="event-recent-user-2",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "r2"},
                attempt_id=None,
                execution_id=None,
            ),
        ),
        policy=_low_history_policy(),
    )

    continuity_texts = tuple(
        item.summary_text for item in snapshot.conversation_continuity.items
    )
    assert continuity_texts == ("old", "r1", "r2")
    assert all(
        item.item_kind is not ConversationContinuityKind.EPISODE_SUMMARY
        for item in snapshot.conversation_continuity.items
    )
    assert any(
        diagnostic.reason is MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
        for diagnostic in snapshot.diagnostics
    )


def test_history_pool_limits_assistant_conclusions_before_episode_summaries() -> None:
    """assistant conclusions 参与 history pool 预算并优先于 episode summaries。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-recent-user",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "recent user"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-final-1",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "aaaa"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-final-2",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "bbbb"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=4,
                event_id="event-episode-budget",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(summary_text="zz"),
                run_id=None,
                attempt_id=None,
                execution_id=None,
            ),
        ),
        policy=_assistant_budget_policy(),
    )

    continuity_texts = tuple(
        item.summary_text for item in snapshot.conversation_continuity.items
    )
    assert continuity_texts == ("recent user", "bbbb")
    assert all(
        item.item_kind is not ConversationContinuityKind.EPISODE_SUMMARY
        for item in snapshot.conversation_continuity.items
    )
    assert any(
        diagnostic.reason is MemoryDiagnosticReason.BUDGET_LIMIT_REACHED
        for diagnostic in snapshot.diagnostics
    )


def test_recent_raw_turns_floor_zero_keeps_no_raw_floor() -> None:
    """recent_raw_turns_floor 为 0 时不通过 ``-0`` 切片保留全部 raw turns。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-user-1",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "u1"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-user-2",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "u2"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=3,
                event_id="event-user-3",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "u3"},
                attempt_id=None,
                execution_id=None,
            ),
        ),
        policy=_zero_recent_floor_policy(),
    )

    continuity_texts = tuple(
        item.summary_text for item in snapshot.conversation_continuity.items
    )
    assert continuity_texts == ("u3",)


def test_recent_raw_turns_support_followup_without_becoming_stable_fact() -> None:
    """recent raw turns 可支持未 compact 追问，但 compact 后不是真源事实。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-user-raw-fact-like",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "the second factor is margin"},
                attempt_id=None,
                execution_id=None,
            ),
            _memory_event(
                event_sequence=2,
                event_id="event-compact-no-fact",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="navigation only",
                    minimum_preserve_items=[
                        _minimum_preserve_item(text="the second factor")
                    ],
                ),
                run_id="run-compact",
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.evidence_backed_facts == ()
    assert any(
        item.item_kind is ConversationContinuityKind.RAW_USER_TURN
        and item.summary_text == "the second factor is margin"
        for item in snapshot.conversation_continuity.items
    )
    assert any(
        item.item_kind is ConversationContinuityKind.MINIMUM_PRESERVE_ITEM
        for item in snapshot.conversation_continuity.items
    )


def test_unknown_event_type_records_diagnostic_and_advances_cursor() -> None:
    """未知 event type 不应静默忽略，且 snapshot cursor 覆盖该事件。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=7,
                event_id="event-unknown",
                event_type="UNKNOWN_MEMORY_EVENT",
                payload={"summary_text": "ignored"},
                run_id=None,
                attempt_id=None,
                execution_id=None,
            ),
        )
    )

    assert snapshot.cursor.checkpoint_event_sequence == 7
    assert snapshot.evidence_backed_facts == ()
    assert snapshot.conversation_continuity.items == ()
    assert len(snapshot.diagnostics) == 1
    assert (
        snapshot.diagnostics[0].reason
        is MemoryDiagnosticReason.UNSUPPORTED_EVENT_TYPE
    )
    assert (
        MemoryExcludedReason.UNSUPPORTED_EVENT_TYPE.value
        in snapshot.diagnostics[0].message
    )


def test_snapshot_rebuild_preserves_provenance_and_digest_is_deterministic() -> None:
    """固定 events 与 policy rebuild 后 digest 稳定且不投影 tool result fact。"""

    events = (
        _memory_event(
            event_sequence=1,
            event_id="event-tool-rebuild",
            event_type="TOOL_RESULT_ACCEPTED",
            payload=_tool_payload(summary="tool supplied neutral summary"),
        ),
        _memory_event(
            event_sequence=2,
            event_id="event-final-rebuild",
            event_type="RUN_SUCCEEDED",
            payload={"final_answer": "assistant conclusion"},
            run_id="run-1",
            attempt_id=None,
            execution_id=None,
        ),
    )
    first = _build_snapshot(events)
    second = build_conversation_memory_snapshot_from_events(
        events=events,
        session_id=_SESSION_ID,
        consumer_id=_CONSUMER_ID,
        policy=_policy(),
        built_at="2026-05-17T00:00:00.000000Z",
    )

    assert first.snapshot_digest == second.snapshot_digest
    assert first.evidence_backed_facts == ()
    assert second.evidence_backed_facts == ()
    assert first.cursor.checkpoint_event_sequence == 2
    assert second.cursor.checkpoint_event_sequence == 2


def test_projection_consumer_writes_snapshot_with_runner_checkpoint(
    tmp_path: Path,
) -> None:
    """ProjectionRunner 可用 memory consumer 从 committed EventLog 构建 snapshot。"""

    policy = _policy()
    consumer = ConversationMemoryProjectionConsumer(policy)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-user-durable",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "durable user input"},
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-tool-durable",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=_tool_payload(summary="durable tool summary"),
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-compact-durable",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="durable compact summary",
                    pinned_patch={
                        "candidate_id": "patch-durable",
                        "current_goal": {
                            "operation": "replace",
                            "value": "durable compact goal",
                            "evidence_refs": ["evidence-1"],
                        },
                    },
                ),
            )
        )
        result = ProjectionRunner(
            store.transaction_runner, (consumer,)
        ).run_once(
            ProjectionConsumerId(CONVERSATION_MEMORY_CONSUMER_ID),
            limit=10,
        )
        read_back = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(policy))
        )
        checkpoint = store.transaction_runner.run_read(_ReadCheckpointOperation())

        assert result.events_applied == 3
        assert read_back is not None
        assert read_back.snapshot.evidence_backed_facts == ()
        assert read_back.snapshot.pinned_state.current_goal == "durable compact goal"
        assert tuple(
            item.summary_text
            for item in read_back.snapshot.conversation_continuity.items
            if item.item_kind is ConversationContinuityKind.EPISODE_SUMMARY
        ) == ("durable compact summary",)
        assert read_back.snapshot.cursor.checkpoint_event_sequence == 3
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 3


def test_durable_roundtrip_uses_evidence_backed_facts_and_item_kind(
    tmp_path: Path,
) -> None:
    """durable snapshot roundtrip 使用 evidence_backed_facts 与新 item kind。"""

    policy = _policy()
    consumer = ConversationMemoryProjectionConsumer(policy)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-compact-durable-fact",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="durable compact fact summary",
                    fact_candidates=[
                        _fact_candidate(
                            candidate_id="durable-fact-candidate",
                            claim_text="Durable fact claim.",
                        )
                    ],
                    minimum_preserve_items=[
                        _minimum_preserve_item(
                            item_id="durable-minimum-preserve",
                            label="durable continuity",
                            text="Durable minimum preserve continuity.",
                        )
                    ],
                ),
            )
        )
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId(CONVERSATION_MEMORY_CONSUMER_ID),
            limit=10,
        )

        read_back = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(policy))
        )
        row = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
                f"""
                SELECT snapshot_json
                FROM {TABLE_HOST_MEMORY_SNAPSHOTS}
                WHERE snapshot_id = ?
                """,
                (
                    "" if read_back is None else read_back.snapshot.snapshot_id,
                ),
            )
        )
        fact_item_kind = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
                f"""
                SELECT item_kind
                FROM {TABLE_HOST_MEMORY_ITEMS}
                WHERE snapshot_id = ?
                  AND item_kind = ?
                """,
                (
                    "" if read_back is None else read_back.snapshot.snapshot_id,
                    "evidence_backed_fact",
                ),
            )
        )
        minimum_preserve_item_kind = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
                f"""
                SELECT item_kind
                FROM {TABLE_HOST_MEMORY_ITEMS}
                WHERE snapshot_id = ?
                  AND item_kind = ?
                """,
                (
                    "" if read_back is None else read_back.snapshot.snapshot_id,
                    "minimum_preserve_item",
                ),
            )
        )

        assert read_back is not None
        assert len(read_back.snapshot.evidence_backed_facts) == 1
        assert read_back.snapshot.evidence_backed_facts[0].claim_text == (
            "Durable fact claim."
        )
        assert any(
            item.item_kind is ConversationContinuityKind.MINIMUM_PRESERVE_ITEM
            and item.summary_text == "Durable minimum preserve continuity."
            for item in read_back.snapshot.conversation_continuity.items
        )
        assert row is not None
        snapshot_json = row.get("snapshot_json")
        assert isinstance(snapshot_json, str)
        assert "evidence_backed_facts" in snapshot_json
        assert "verified_facts" not in snapshot_json
        assert fact_item_kind is not None
        assert fact_item_kind.get("item_kind") == "evidence_backed_fact"
        assert minimum_preserve_item_kind is not None
        assert (
            minimum_preserve_item_kind.get("item_kind")
            == "minimum_preserve_item"
        )


def test_old_snapshot_verified_facts_key_fails_closed() -> None:
    """旧 verified_facts snapshot JSON key 必须明确失败。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-user-old-key",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "user"},
                attempt_id=None,
                execution_id=None,
            ),
        )
    )
    value = conversation_memory_snapshot_to_json_value(snapshot)
    assert isinstance(value, dict)
    value["verified_facts"] = []

    with pytest.raises(ValueError, match="old verified_facts snapshot key"):
        conversation_memory_snapshot_from_json_value(value)


def test_old_durable_verified_fact_item_kind_fails_closed(tmp_path: Path) -> None:
    """旧 durable item kind verified_fact 必须明确失败。"""

    snapshot = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-compact-old-kind",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary",
                    fact_candidates=[_fact_candidate()],
                ),
            ),
        )
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-compact-old-kind",
                event_type="CONTEXT_COMPACTED",
                payload=_compact_payload(
                    summary_text="summary",
                    fact_candidates=[_fact_candidate()],
                ),
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: write_memory_snapshot_with_checkpoint(
                transaction,
                snapshot,
                now=_NOW,
            )
        )
        store.transaction_runner.run_write(
            _ForceOldVerifiedFactItemKindOperation(snapshot.snapshot_id)
        )

        with pytest.raises(
            HostDurableError,
            match="old durable memory item kind verified_fact",
        ):
            store.transaction_runner.run_read(
                _ReadLatestSnapshotOperation(
                    digest_memory_projection_policy(_policy())
                )
            )


def test_memory_projection_filter_includes_compacted_but_not_failed() -> None:
    """生产 memory consumer 消费 compacted，但不消费 compaction failed。"""

    consumer = ConversationMemoryProjectionConsumer(_policy())
    event_types = consumer.event_filter.class_filters[0].event_types

    assert event_types is not None
    assert "CONTEXT_COMPACTED" in event_types
    assert "CONTEXT_COMPACTION_FAILED" not in event_types


def test_preview_reasoning_and_display_only_events_do_not_enter_memory(
    tmp_path: Path,
) -> None:
    """preview / reasoning / display-only events 不进入 memory snapshot。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 非 canonical display-only 事件进入 memory 时抛出。
    """

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-preview-content",
                event_type="CONTENT_DELTA",
                payload={"display_text": "ignored content preview"},
                event_class=EventClass.PREVIEW,
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-preview-reasoning",
                event_type="REASONING_DELTA",
                payload={"display_text": "ignored reasoning preview"},
                event_class=EventClass.PREVIEW,
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-display-only-final",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "ignored display-only conclusion"},
                event_class=EventClass.DIAGNOSTIC,
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-canonical-user",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "canonical user fact"},
            )
        )

        result = catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=8,
        )
        read_back = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(policy))
        )

        assert result.events_scanned == 4
        assert result.events_matched == 1
        assert read_back is not None
        assert read_back.snapshot.pinned_state.current_goal == "canonical user fact"
        assert read_back.snapshot.evidence_backed_facts == ()
        assert tuple(
            item.summary_text
            for item in read_back.snapshot.conversation_continuity.items
        ) == ("canonical user fact",)


def test_reset_conversation_memory_projection_deletes_consumer_scope_only(
    tmp_path: Path,
) -> None:
    """reset 清目标 consumer 全部 policy snapshot，但保留其它 consumer rows。"""

    target_policy = _policy()
    other_policy = _low_history_policy()
    other_consumer_id = "host.memory.other-consumer"
    target = _build_snapshot(
        (
            _memory_event(
                event_sequence=1,
                event_id="event-target-reset",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "target memory"},
                attempt_id=None,
                execution_id=None,
            ),
        ),
        policy=target_policy,
    )
    other_consumer = build_conversation_memory_snapshot_from_events(
        events=(
            _memory_event(
                event_sequence=2,
                event_id="event-other-consumer-reset",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "other consumer memory"},
                attempt_id=None,
                execution_id=None,
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=other_consumer_id,
        policy=target_policy,
        built_at=_NOW,
    )
    other_policy_snapshot = build_empty_conversation_memory_snapshot(
        snapshot_id="snapshot-other-policy-reset",
        session_id=_SESSION_ID,
        consumer_id=_CONSUMER_ID,
        policy_digest=digest_memory_projection_policy(other_policy),
        built_at=_NOW,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-target-reset",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "target memory"},
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-other-consumer-reset",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "other consumer memory"},
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: write_memory_snapshot_with_checkpoint(
                transaction,
                target,
                now=_NOW,
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: write_memory_snapshot_with_checkpoint(
                transaction,
                other_consumer,
                now=_NOW,
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: write_memory_snapshot_with_checkpoint(
                transaction,
                other_policy_snapshot,
                now=_NOW,
            )
        )

        store.transaction_runner.run_write(
            lambda transaction: reset_conversation_memory_projection(
                transaction,
                consumer_id=_CONSUMER_ID,
            )
        )
        target_read = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(target_policy))
        )
        other_policy_read = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(other_policy))
        )
        other_consumer_read = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=other_consumer_id,
                policy_digest=digest_memory_projection_policy(target_policy),
            )
        )
        target_checkpoint = store.transaction_runner.run_read(
            _ReadCheckpointForConsumerOperation(_CONSUMER_ID)
        )
        other_checkpoint = store.transaction_runner.run_read(
            _ReadCheckpointForConsumerOperation(other_consumer_id)
        )

        assert target_read is None
        assert other_policy_read is None
        assert other_consumer_read is not None
        assert target_checkpoint is None
        assert other_checkpoint is not None


def test_rebuild_conversation_memory_projection_is_stable_and_does_not_append_eventlog(
    tmp_path: Path,
) -> None:
    """rebuild 从 committed EventLog 重建 snapshot，保留 provenance 且不写 EventLog。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-tool-rebuild-service",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=_tool_payload(summary="service rebuild tool summary"),
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-final-rebuild-service",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "service rebuild conclusion"},
            )
        )
        before_count = store.transaction_runner.run_read(_event_log_count)

        first = rebuild_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=1,
        )
        first_snapshot = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(policy))
        )
        second = rebuild_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=2,
        )
        second_snapshot = store.transaction_runner.run_read(
            _ReadLatestSnapshotOperation(digest_memory_projection_policy(policy))
        )
        after_count = store.transaction_runner.run_read(_event_log_count)
        checkpoint = store.transaction_runner.run_read(_ReadCheckpointOperation())

        assert first.failures == 0
        assert second.failures == 0
        assert first_snapshot is not None
        assert second_snapshot is not None
        assert first_snapshot.snapshot.snapshot_digest == (
            second_snapshot.snapshot.snapshot_digest
        )
        assert first_snapshot.snapshot.evidence_backed_facts == ()
        assert before_count == after_count
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == (
            second_snapshot.snapshot.cursor.checkpoint_event_sequence
        )


def test_catch_up_projection_failure_row_remains_observable(tmp_path: Path) -> None:
    """consumer apply 失败时 catch-up 返回 failure 且 projection failure row 可读。"""

    policy = _policy()
    policy_digest = digest_memory_projection_policy(policy)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-before-damage",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "before damage"},
            )
        )
        rebuild_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=8,
        )
        store.transaction_runner.run_write(
            lambda transaction: _damage_latest_memory_snapshot(
                transaction,
                policy_digest=policy_digest,
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: _append_memory_event(
                transaction,
                event_id="event-after-damage",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "after damage"},
            )
        )

        result = catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=8,
        )
        failure = store.transaction_runner.run_read(
            _ReadProjectionFailureOperation(_CONSUMER_ID)
        )

        assert result.failures == 1
        assert failure is not None
        assert failure.failed_event_id == "event-after-damage"
        assert failure.last_error_code == "HostDurableError"
