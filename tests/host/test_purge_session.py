"""P15 purge durable tombstone primitive 测试。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.idempotency import (
    IdempotencyResultRef,
    IdempotencyScope,
    IdempotencyStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.purge import (
    PURGE_IDEMPOTENCY_RESULT_KIND,
    PURGE_IDEMPOTENCY_SCOPE_KIND,
    PurgeDeleteCounts,
    PurgeReplayDecision,
    PurgeReplayDecisionKind,
    PurgeTombstoneRow,
    build_deleted_counts_digest,
    build_purge_semantic_digest,
    insert_purge_tombstone,
    read_purge_tombstone_by_id,
    read_purge_tombstone_by_session_id,
    record_or_read_purge_idempotency,
)
from dayu.host.durable.transaction import HostTransaction

_SESSION_ID = "session-purged-1"
_CLIENT_REQUEST_ID = "purge-request-1"
_OTHER_CLIENT_REQUEST_ID = "purge-request-2"
_REASON = "user requested durable retention purge"
_PURGED_AT = "2026-05-29T00:00:00.000000Z"
_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_DIGEST_C = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"


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


def _counts() -> PurgeDeleteCounts:
    """构造稳定的删除计数样本。

    :returns: purge 删除计数。
    """

    return PurgeDeleteCounts(
        event_log_rows=3,
        idempotency_records=1,
        payload_descriptors=2,
        sqlite_payloads=2,
        host_session_slots=1,
        host_sessions=1,
        host_runs=2,
        host_attempts=2,
        host_attempt_dispatch_records=2,
        host_wait_records=1,
        host_run_results=2,
        host_session_timeline_items=5,
        host_memory_snapshots=1,
        host_memory_items=4,
        host_memory_diagnostics=1,
        host_audit_sink_markers=3,
        host_tool_trace_hot=2,
        host_outbox_terminal_items=1,
        host_outbox_drain_idempotency=1,
        host_projection_checkpoints=1,
        host_projection_failures=1,
    )


def _operation_context_refs() -> dict[str, JsonValue]:
    """构造 operation context refs JSON。

    :returns: operation context refs JSON object。
    """

    return {"request_ref": "purge-context-1", "source": "test"}


def _request_context() -> dict[str, JsonValue]:
    """构造 request context JSON。

    :returns: request context JSON object。
    """

    return {"actor_ref": "user-1", "ui_request_ref": "button-1"}


def _semantic_digest(reason: str = _REASON) -> str:
    """构造测试用 purge semantic digest。

    :param reason: purge 原因。
    :returns: semantic digest。
    """

    return build_purge_semantic_digest(
        session_id=_SESSION_ID,
        reason=reason,
        operation_context_digest=_DIGEST_A,
        operation_context_refs=_operation_context_refs(),
        request_context=_request_context(),
    )


def _tombstone(
    *,
    client_request_id: str = _CLIENT_REQUEST_ID,
    semantic_digest: str | None = None,
) -> PurgeTombstoneRow:
    """构造测试用 tombstone row。

    :param client_request_id: purge 请求幂等 key。
    :param semantic_digest: semantic digest；未提供时使用默认 digest。
    :returns: purge tombstone row。
    """

    counts = _counts()
    effective_semantic_digest = (
        _semantic_digest() if semantic_digest is None else semantic_digest
    )
    return PurgeTombstoneRow(
        tombstone_id="purge-tombstone-1",
        session_id=_SESSION_ID,
        client_request_id=client_request_id,
        semantic_request_digest=effective_semantic_digest,
        actor="user-1",
        source="host-api",
        operation_context_digest=_DIGEST_A,
        operation_context_refs=_operation_context_refs(),
        reason=_REASON,
        purged_at=_PURGED_AT,
        precondition_digest=_DIGEST_B,
        deleted_counts=counts,
        deleted_counts_digest=build_deleted_counts_digest(counts),
        deleted_refs_digest=_DIGEST_C,
        audit_record_ref=None,
        audit_record_digest=None,
        request_context=_request_context(),
    )


class _InsertAndReadTombstoneOperation:
    """插入并读取 tombstone 的测试 transaction operation。"""

    def __call__(
        self, transaction: HostTransaction
    ) -> tuple[PurgeTombstoneRow, PurgeTombstoneRow | None]:
        """执行插入并按 Session id 读取。

        :param transaction: Host durable transaction。
        :returns: 插入 row 与按 Session 读取的 row。
        """

        inserted = insert_purge_tombstone(transaction, _tombstone())
        by_session = read_purge_tombstone_by_session_id(
            transaction,
            _SESSION_ID,
        )
        by_id = read_purge_tombstone_by_id(transaction, inserted.tombstone_id)
        assert by_id == inserted
        return inserted, by_session


class _InsertTombstoneOnlyOperation:
    """只插入 tombstone 的测试 transaction operation。"""

    def __init__(
        self,
        *,
        client_request_id: str = _CLIENT_REQUEST_ID,
        semantic_digest: str | None = None,
    ) -> None:
        """初始化 operation。

        :param client_request_id: purge 请求幂等 key。
        :param semantic_digest: semantic digest。
        :returns: ``None``。
        """

        self._client_request_id = client_request_id
        self._semantic_digest = semantic_digest

    def __call__(self, transaction: HostTransaction) -> PurgeTombstoneRow:
        """执行 tombstone 插入。

        :param transaction: Host durable transaction。
        :returns: 插入后的 tombstone row。
        """

        return insert_purge_tombstone(
            transaction,
            _tombstone(
                client_request_id=self._client_request_id,
                semantic_digest=self._semantic_digest,
            ),
        )


class _RecordOrReadOperation:
    """执行 purge idempotency replay helper 的测试 operation。"""

    def __init__(self, *, client_request_id: str, semantic_digest: str) -> None:
        """初始化 operation。

        :param client_request_id: purge 请求幂等 key。
        :param semantic_digest: semantic digest。
        :returns: ``None``。
        """

        self._client_request_id = client_request_id
        self._semantic_digest = semantic_digest

    def __call__(self, transaction: HostTransaction) -> PurgeReplayDecision:
        """执行 replay helper。

        :param transaction: Host durable transaction。
        :returns: purge replay 判定。
        """

        return record_or_read_purge_idempotency(
            transaction,
            session_id=_SESSION_ID,
            client_request_id=self._client_request_id,
            semantic_request_digest=self._semantic_digest,
        )


class _SeedIdempotencyOnlyOperation:
    """只写入 purge idempotency row 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """写入 result_ref 指向缺失 tombstone 的幂等 row。

        :param transaction: Host durable transaction。
        :returns: ``None``。
        """

        IdempotencyStore().record_idempotent_result(
            transaction,
            IdempotencyScope(
                scope_kind=PURGE_IDEMPOTENCY_SCOPE_KIND,
                scope_id=_SESSION_ID,
                idempotency_key=_CLIENT_REQUEST_ID,
            ),
            _semantic_digest(),
            IdempotencyResultRef(
                result_kind=PURGE_IDEMPOTENCY_RESULT_KIND,
                result_ref="missing-tombstone",
                created_event_id=None,
                created_event_sequence=None,
            ),
        )


class _SeedTombstoneWithConflictingIdempotencyOperation:
    """写入 tombstone 与同 scope/key 不同 digest 幂等 row 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """写入内部不一致的 tombstone / idempotency 组合。

        :param transaction: Host durable transaction。
        :returns: ``None``。
        """

        tombstone = insert_purge_tombstone(transaction, _tombstone())
        IdempotencyStore().record_idempotent_result(
            transaction,
            IdempotencyScope(
                scope_kind=PURGE_IDEMPOTENCY_SCOPE_KIND,
                scope_id=_SESSION_ID,
                idempotency_key=_CLIENT_REQUEST_ID,
            ),
            build_purge_semantic_digest(
                session_id=_SESSION_ID,
                reason="different durable row digest",
                operation_context_digest=_DIGEST_A,
                operation_context_refs=_operation_context_refs(),
                request_context=_request_context(),
            ),
            IdempotencyResultRef(
                result_kind=PURGE_IDEMPOTENCY_RESULT_KIND,
                result_ref=tombstone.tombstone_id,
                created_event_id=None,
                created_event_sequence=None,
            ),
        )


class _InsertMalformedTombstoneOperation:
    """尝试插入 malformed tombstone 的测试 operation。"""

    def __init__(self, tombstone: PurgeTombstoneRow) -> None:
        """初始化 operation。

        :param tombstone: 待插入的 malformed tombstone。
        :returns: ``None``。
        """

        self._tombstone = tombstone

    def __call__(self, transaction: HostTransaction) -> PurgeTombstoneRow:
        """执行 malformed tombstone 插入。

        :param transaction: Host durable transaction。
        :returns: 插入后的 tombstone row。
        :raises HostDurableError: tombstone validation 失败时抛出。
        """

        return insert_purge_tombstone(transaction, self._tombstone)


def test_insert_and_read_purge_tombstone_round_trip(tmp_path: Path) -> None:
    """tombstone 可在无 Session / EventLog row 时插入并按 id/session 读取。"""

    result: tuple[PurgeTombstoneRow, PurgeTombstoneRow | None] | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        result = store.transaction_runner.run_write(
            _InsertAndReadTombstoneOperation()
        )

    assert result is not None
    inserted, by_session = result
    assert by_session == inserted
    assert inserted.session_id == _SESSION_ID
    assert inserted.deleted_counts.event_log_rows == 3
    assert inserted.deleted_counts_digest == build_deleted_counts_digest(
        inserted.deleted_counts
    )


def test_tombstone_replay_records_purge_idempotency_with_null_event_refs(
    tmp_path: Path,
) -> None:
    """tombstone 存在但幂等 row 缺失时，同 key/digest 从 tombstone replay。"""

    semantic_digest = _semantic_digest()
    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_InsertTombstoneOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=semantic_digest,
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.REPLAY_TOMBSTONE
    assert decision.tombstone is not None
    assert decision.tombstone.tombstone_id == "purge-tombstone-1"
    assert decision.idempotency_record is not None
    assert decision.idempotency_record.result_kind == PURGE_IDEMPOTENCY_RESULT_KIND
    assert decision.idempotency_record.created_event_id is None
    assert decision.idempotency_record.created_event_sequence is None


def test_tombstone_same_key_different_digest_conflicts(tmp_path: Path) -> None:
    """tombstone 存在但同 key digest 不同时返回幂等冲突判定。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_InsertTombstoneOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=build_purge_semantic_digest(
                    session_id=_SESSION_ID,
                    reason="different purge reason",
                    operation_context_digest=_DIGEST_A,
                    operation_context_refs=_operation_context_refs(),
                    request_context=_request_context(),
                ),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT
    assert decision.tombstone is not None
    assert decision.idempotency_record is None


def test_tombstone_different_key_returns_already_purged_conflict(
    tmp_path: Path,
) -> None:
    """tombstone 存在但 client_request_id 不同时返回 already-purged conflict。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_InsertTombstoneOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_OTHER_CLIENT_REQUEST_ID,
                semantic_digest=_semantic_digest(),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.ALREADY_PURGED_CONFLICT
    assert decision.tombstone is not None
    assert decision.idempotency_record is None


def test_existing_idempotency_same_key_different_digest_conflicts(
    tmp_path: Path,
) -> None:
    """无 tombstone 但同 key 幂等 row digest 不同时返回幂等冲突。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedIdempotencyOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=build_purge_semantic_digest(
                    session_id=_SESSION_ID,
                    reason="different purge reason",
                    operation_context_digest=_DIGEST_A,
                    operation_context_refs=_operation_context_refs(),
                    request_context=_request_context(),
                ),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT
    assert decision.tombstone is None
    assert decision.idempotency_record is not None


def test_tombstone_same_key_same_digest_with_conflicting_idempotency_is_inconsistent(
    tmp_path: Path,
) -> None:
    """tombstone 同 key/digest 但幂等表内不同 digest 时返回 durable inconsistency。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            _SeedTombstoneWithConflictingIdempotencyOperation()
        )
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=_semantic_digest(),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.DURABLE_INCONSISTENCY
    assert decision.tombstone is not None
    assert decision.idempotency_record is None


def test_deleted_counts_digest_rejects_negative_counts() -> None:
    """deleted counts digest 拒绝负数计数。"""

    with pytest.raises(HostDurableError):
        build_deleted_counts_digest(replace(_counts(), event_log_rows=-1))


def test_insert_tombstone_rejects_mismatched_deleted_counts_digest(
    tmp_path: Path,
) -> None:
    """tombstone validation 拒绝 deleted_counts_digest 与 counts 不匹配。"""

    malformed = replace(_tombstone(), deleted_counts_digest=_DIGEST_A)
    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                _InsertMalformedTombstoneOperation(malformed)
            )


def test_insert_tombstone_rejects_unpaired_audit_record_ref(
    tmp_path: Path,
) -> None:
    """tombstone validation 拒绝 audit_record_ref / digest 单边存在。"""

    ref_only = replace(_tombstone(), audit_record_ref="audit-record-1")
    digest_only = replace(_tombstone(), audit_record_digest=_DIGEST_A)
    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                _InsertMalformedTombstoneOperation(ref_only)
            )
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                _InsertMalformedTombstoneOperation(digest_only)
            )
