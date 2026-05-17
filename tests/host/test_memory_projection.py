"""Host memory projection contracts 与 durable primitive 测试。"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import cast

import pytest

from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.memory import (
    MemoryDiagnosticRow,
    MemorySnapshotRow,
    read_latest_memory_snapshot,
    read_memory_diagnostic,
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
    read_projection_checkpoint,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import (
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
    MemoryProducerKind,
    MemoryProjectionPolicy,
    MemoryProvenanceRef,
    MemorySizeUnits,
    MemorySnapshotCursor,
    OpaqueMemoryRef,
    PinnedStateView,
    VerifiedFactView,
    WorkingAssumptionView,
    build_empty_conversation_memory_snapshot,
    calculate_memory_snapshot_digest,
    digest_memory_projection_policy,
    estimate_memory_size_units,
)

_CONSUMER_ID = "host.memory.session.v1"
_SESSION_ID = "session-1"
_NOW = "2026-05-16T00:00:00.000000Z"
_FORBIDDEN_BUSINESS_TERMS = (
    "company",
    "business_line",
    "technology_release",
)


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
        max_pinned_items=8,
        max_verified_facts=16,
        max_working_assumptions=8,
        recent_raw_turns_floor=2,
        max_raw_turn_size_units=1024,
        history_pool_size_units=4096,
        stable_layer_size_units=2048,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
    )


def _tool_provenance() -> MemoryProvenanceRef:
    """构造 TOOL provenance。

    :returns: TOOL provenance ref。
    """

    return MemoryProvenanceRef(
        producer_kind=MemoryProducerKind.TOOL,
        producer_name="tool-a",
        event_id="event-1",
        event_sequence=1,
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        tool_result_ref="event-1",
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
        assert read_back.snapshot.verified_facts == ()
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


def test_typed_contracts_reject_invalid_ids_cursor_and_verified_fact() -> None:
    """typed contracts 拒绝空 id、非法 cursor 与非 TOOL verified fact。"""

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
        VerifiedFactView(
            item_id="fact-1",
            fact_summary="summary",
            claim_status=MemoryClaimStatus.ASSUMPTION,
            provenance=_tool_provenance(),
            evidence_anchor=None,
            subject_refs=(),
            included_reason=MemoryIncludedReason.TOOL_VERIFIED_FACT,
            excluded_reason=None,
            size_units=MemorySizeUnits(units=7),
        )
    with pytest.raises(ValueError):
        VerifiedFactView(
            item_id="fact-1",
            fact_summary="summary",
            claim_status=MemoryClaimStatus.TOOL_VERIFIED,
            provenance=_user_provenance(),
            evidence_anchor=None,
            subject_refs=(),
            included_reason=MemoryIncludedReason.TOOL_VERIFIED_FACT,
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
    with pytest.raises(ValueError):
        PinnedStateView(
            current_goal=None,
            confirmed_subjects=(),
            user_constraints=(),
            open_questions=("question", "question"),
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
            VerifiedFactView,
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
        verified_facts=(),
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
        verified_facts=(),
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
                payload_ref=None,
                payload_digest=None,
                included_reason=None,
                excluded_reason=MemoryExcludedReason.POLICY_EXCLUDED,
                size_units=estimate_memory_size_units("summary"),
            )
