"""Host ToolRuntime accept barrier 测试。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.api import EnsureSessionRequest
from dayu.host._event_payload import payload_object
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.memory import read_latest_memory_snapshot
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CreateRunningRunInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    RunStartReason,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.evidence import accepted_evidence_envelope_from_json_value
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from dayu.host.memory_repair import ConversationMemoryProjectionCatchupPort
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.tool_runtime import (
    DefaultHostToolFactAcceptPort,
    DuplicateDecisionKind,
    HostEventRef,
    ToolAcceptRejectReason,
    ToolAcceptRetryPolicy,
    ToolFactAcceptTimedOut,
    ToolFactAcceptCandidate,
    ToolFactAcceptedAck,
    ToolFactKind,
    ToolFactRejectedAck,
    ToolPolicyDecision,
    ToolPolicyDecisionKind,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "tool-accept-test"})


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 active Run 引用。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


@dataclass(slots=True)
class _FailingProjectionCatchup(ProjectionCatchupPort):
    """测试用失败 projection catch-up port。"""

    calls: int = 0

    def catch_up_projection(self) -> None:
        """记录调用并模拟 catch-up 失败。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出测试错误。
        """

        self.calls += 1
        raise RuntimeError("forced tool accept projection catch-up failure")


def test_same_accept_key_and_digest_returns_existing_ack_without_duplicate_facts(
    tmp_path: Path,
) -> None:
    """同 accept key + 同 semantic digest 返回既有 ack 且不重复写工具事实。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _completed_candidate(seeded, tool_call_id="tool-call-1")
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        first = accept_port.accept_tool_fact(candidate)
        before = _tool_events(store.transaction_runner)
        second = accept_port.accept_tool_fact(candidate)
        after = _tool_events(store.transaction_runner)

        assert isinstance(first, ToolFactAcceptedAck)
        assert isinstance(second, ToolFactAcceptedAck)
        assert second.accepted_event_refs == first.accepted_event_refs
        assert after == before
        assert [row.event_type for row in after] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
        ]
        assert all(row.event_class is EventClass.CANONICAL_FACT for row in after)


def test_tool_fact_accept_survives_projection_catchup_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TOOL_RESULT_ACCEPTED 后 projection catch-up 失败不影响 accept ack。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        projection = _FailingProjectionCatchup()
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner,
            projection_catchup_port=projection,
        )

        with caplog.at_level("WARNING", logger="dayu.host.projection"):
            result = accept_port.accept_tool_fact(
                _completed_candidate(seeded, tool_call_id="tool-call-catchup")
            )

        assert isinstance(result, ToolFactAcceptedAck)
        assert result.tool_result_event_ref is not None
        assert projection.calls == 1
        assert [row.event_type for row in _tool_events(store.transaction_runner)] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
        ]
        assert "projection catch-up failed; continuing" in caplog.text
        assert all(record.levelname == "WARNING" for record in caplog.records)


def test_tool_result_accepted_payload_carries_accepted_evidence_envelope(
    tmp_path: Path,
) -> None:
    """新 accepted result payload 携带稳定 accepted evidence envelope。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _completed_candidate(seeded, tool_call_id="tool-call-evidence")
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)
        result_rows = _tool_result_events(store.transaction_runner)

        assert isinstance(result, ToolFactAcceptedAck)
        assert result.tool_result_event_ref is not None
        assert len(result_rows) == 1
        payload = payload_object(result_rows[0])
        envelope_json = payload["accepted_evidence_envelope"]
        envelope = accepted_evidence_envelope_from_json_value(envelope_json)
        assert envelope.evidence_id == (
            f"evidence:{result.tool_result_event_ref.event_id}"
        )
        assert envelope.producer_event_ref == result.tool_result_event_ref.event_id
        assert envelope.tool_name == "lookup"
        assert envelope.tool_call_id == "tool-call-evidence"
        assert envelope.tool_query.tool_call_requested_event_ref == (
            result.tool_call_requested_event_ref.event_id
        )
        assert envelope.tool_query.normalized_arguments_digest == (
            candidate.normalized_arguments_digest
        )
        assert envelope.tool_query.semantic_input_digest == (
            candidate.semantic_input_digest
        )
        assert envelope.result_ref.payload_ref is None
        assert envelope.result_ref.payload_digest == candidate.payload_digest
        assert envelope.result_ref.outcome_digest == candidate.outcome_digest
        assert envelope.result_ref.truncation_applied is False
        assert envelope.source_refs == ()
        assert envelope.locator_refs == ()


def test_accepted_evidence_envelope_codec_rejects_partial_object() -> None:
    """accepted evidence envelope JSON codec 拒绝不完整对象。"""

    with pytest.raises(ValueError, match="unexpected JSON fields"):
        accepted_evidence_envelope_from_json_value(
            {"evidence_id": "evidence:event-tool-result"}
        )


def test_tool_fact_accept_logs_ids_without_tool_payload(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """工具事实 accept 日志记录 ids / refs，不记录工具结果 payload。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 日志缺少字段或泄漏 payload 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.tool_runtime"):
            result = accept_port.accept_tool_fact(
                _completed_candidate(seeded, tool_call_id="tool-call-logging")
            )

        assert isinstance(result, ToolFactAcceptedAck)
        assert "host.tool_runtime.accept_tool_fact.accepted" in caplog.text
        assert "host.tool_runtime.accept_tool_fact.committed" in caplog.text
        assert seeded.run_id in caplog.text
        assert seeded.attempt_id in caplog.text
        assert "tool_call_id=tool-call-logging" in caplog.text
        assert "tool_name=lookup" in caplog.text
        assert "{\"outcome\":" not in caplog.text
        assert "{\"payload\":" not in caplog.text


def test_tool_fact_accept_concrete_memory_catchup_does_not_project_fact(
    tmp_path: Path,
) -> None:
    """TOOL_RESULT_ACCEPTED commit 后 concrete catch-up 不直接写入 fact。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: accepted 工具事实被 memory catch-up 直接投影时抛出。
    """

    policy = default_memory_projection_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner,
            projection_catchup_port=ConversationMemoryProjectionCatchupPort(
                transaction_runner=store.transaction_runner,
                policy=policy,
                batch_size=8,
            ),
        )

        result = accept_port.accept_tool_fact(
            _completed_candidate(seeded, tool_call_id="tool-call-memory-catchup")
        )
        snapshot = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=seeded.session_id,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert isinstance(result, ToolFactAcceptedAck)
        assert result.tool_result_event_ref is not None
        assert snapshot is not None
        assert snapshot.snapshot.evidence_backed_facts == ()
        assert snapshot.snapshot.cursor.checkpoint_event_id == (
            result.tool_result_event_ref.event_id
        )


def test_same_accept_key_with_different_digest_returns_idempotency_conflict(
    tmp_path: Path,
) -> None:
    """同 accept key + 不同 semantic digest 返回 rejected ack 且不追加事件。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _completed_candidate(seeded, tool_call_id="tool-call-1")
        conflict = replace(
            candidate,
            semantic_input_digest=sha256_digest_json({"semantic": "changed"}),
            outcome_digest=sha256_digest_json({"outcome": "changed"}),
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        first = accept_port.accept_tool_fact(candidate)
        before = _tool_events(store.transaction_runner)
        second = accept_port.accept_tool_fact(conflict)
        after = _tool_events(store.transaction_runner)

        assert isinstance(first, ToolFactAcceptedAck)
        assert isinstance(second, ToolFactRejectedAck)
        assert second.reason_code is ToolAcceptRejectReason.IDEMPOTENCY_CONFLICT
        assert after == before


def test_invalid_attempt_and_stale_execution_reject_without_tool_facts(
    tmp_path: Path,
) -> None:
    """不存在 Attempt 与 stale execution 都返回 rejected ack。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        base = _completed_candidate(seeded, tool_call_id="tool-call-1")
        invalid_attempt = replace(
            base,
            attempt_id="attempt-missing",
            accept_idempotency_key="accept-missing",
        )
        stale_execution = replace(
            base,
            execution_id="execution-stale",
            tool_call_id="tool-call-stale",
            accept_idempotency_key="accept-stale",
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        invalid = accept_port.accept_tool_fact(invalid_attempt)
        stale = accept_port.accept_tool_fact(stale_execution)

        assert isinstance(invalid, ToolFactRejectedAck)
        assert invalid.reason_code is ToolAcceptRejectReason.INVALID_ATTEMPT
        assert isinstance(stale, ToolFactRejectedAck)
        assert stale.reason_code is ToolAcceptRejectReason.STALE_EXECUTION
        assert _tool_events(store.transaction_runner) == ()


def test_event_sequence_monotonic_and_reuse_has_canonical_governance_only(
    tmp_path: Path,
) -> None:
    """工具 facts 使用 EventLog 全局递增序号，reuse 不伪造新 result fact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )
        completed = _completed_candidate(seeded, tool_call_id="tool-call-1")
        first = accept_port.accept_tool_fact(completed)
        assert isinstance(first, ToolFactAcceptedAck)
        assert first.tool_result_event_ref is not None
        reuse = _reuse_candidate(
            seeded,
            tool_call_id="tool-call-2",
            prior_ref=first.tool_result_event_ref,
        )

        second = accept_port.accept_tool_fact(reuse)
        tool_events = _tool_events(store.transaction_runner)

        assert isinstance(second, ToolFactAcceptedAck)
        assert second.tool_result_event_ref is None
        assert [row.event_sequence for row in tool_events] == sorted(
            row.event_sequence for row in tool_events
        )
        assert all(row.event_class is EventClass.CANONICAL_FACT for row in tool_events)
        assert [row.event_type for row in tool_events] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
            "TOOL_CALL_REQUESTED",
            "TOOL_CALL_GOVERNED",
        ]


def test_duplicate_allow_does_not_append_governed_event(tmp_path: Path) -> None:
    """duplicate allow 只是允许继续执行，不写治理事实污染 event stream。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )
        candidate = replace(
            _completed_candidate(seeded, tool_call_id="tool-call-allow"),
            duplicate_key="duplicate-lookup-MSFT",
            duplicate_decision=DuplicateDecisionKind.ALLOW,
        )

        result = accept_port.accept_tool_fact(candidate)
        tool_events = _tool_events(store.transaction_runner)

        assert isinstance(result, ToolFactAcceptedAck)
        assert [row.event_type for row in tool_events] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
        ]


def test_failed_cancelled_and_governed_error_are_accepted_as_result_facts(
    tmp_path: Path,
) -> None:
    """failed、cancelled 与 governed_error 均写入对应 result fact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )
        candidates = (
            _fact_kind_candidate(
                seeded,
                tool_call_id="tool-call-failed",
                fact_kind=ToolFactKind.FAILED,
                policy_kind=ToolPolicyDecisionKind.ALLOW,
            ),
            _fact_kind_candidate(
                seeded,
                tool_call_id="tool-call-cancelled",
                fact_kind=ToolFactKind.CANCELLED,
                policy_kind=ToolPolicyDecisionKind.ALLOW,
            ),
            _fact_kind_candidate(
                seeded,
                tool_call_id="tool-call-governed-error",
                fact_kind=ToolFactKind.GOVERNED_ERROR,
                policy_kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
            ),
        )

        results = tuple(accept_port.accept_tool_fact(candidate) for candidate in candidates)
        result_rows = _tool_result_events(store.transaction_runner)
        payloads = tuple(payload_object(row) for row in result_rows)

        assert all(isinstance(result, ToolFactAcceptedAck) for result in results)
        assert tuple(payload["tool_fact_kind"] for payload in payloads) == (
            ToolFactKind.FAILED.value,
            ToolFactKind.CANCELLED.value,
            ToolFactKind.GOVERNED_ERROR.value,
        )
        assert payloads[-1]["policy_decision"] == {
            "kind": ToolPolicyDecisionKind.GOVERNED_ERROR.value,
            "reason_code": "governed_error",
            "message": "governed_error",
        }


def test_non_reuse_fact_rejects_prior_reuse_refs(tmp_path: Path) -> None:
    """非 reuse fact kind 不允许携带 prior reuse refs。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )
        completed = _completed_candidate(seeded, tool_call_id="tool-call-1")
        accepted = accept_port.accept_tool_fact(completed)

        assert isinstance(accepted, ToolFactAcceptedAck)
        assert accepted.tool_result_event_ref is not None
        with pytest.raises(ValueError, match="must not carry prior reuse refs"):
            replace(
                _fact_kind_candidate(
                    seeded,
                    tool_call_id="tool-call-failed",
                    fact_kind=ToolFactKind.FAILED,
                    policy_kind=ToolPolicyDecisionKind.ALLOW,
                ),
                reuse_prior_event_refs=(accepted.tool_result_event_ref,),
            )


def test_accept_retry_policy_and_timeout_guard_invalid_values() -> None:
    """accept retry policy 与 timeout ack 拒绝非法参数。"""

    with pytest.raises(ValueError, match="max_attempts"):
        ToolAcceptRetryPolicy(max_attempts=0, backoff_seconds=0.0)
    with pytest.raises(ValueError, match="backoff_seconds"):
        ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=-0.1)
    with pytest.raises(ValueError, match="attempt_count"):
        ToolFactAcceptTimedOut(
            attempt_count=0,
            last_error_code=None,
            diagnostic_refs=(),
        )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _seed_active_run(transaction_runner: HostTransactionRunner) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :returns: seeded run。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="tool-accept", metadata=()),
    ).snapshot.session_id
    seeded = _SeededRun(
        session_id=session_id,
        run_id="run-tool-accept",
        attempt_id="attempt-tool-accept",
        execution_id="execution-tool-accept",
        dispatch_record_id="dispatch-tool-accept",
    )

    def _operation(transaction: HostTransaction) -> None:
        """写入 active Run 所需 durable rows。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        input_event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-input-tool-accept",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-tool-accept",
                idempotency_key="idem-tool-accept-input",
                policy_decision=None,
                reason=None,
                payload_json={"display_text": "hello"},
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=seeded.run_id,
                client_request_id="client-tool-accept",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-tool-accept",
                run_started_event_id="event-run-started-tool-accept",
                attempt_started_event_id="event-attempt-started-tool-accept",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-tool-accept",
                execution_target="target-tool-accept",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            lane_claim_id="claim-test",
            lane_owner_id="owner-test",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-tool-accept",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
                local_worker_id="local-worker-tool-accept",
            ),
        )

    transaction_runner.run_write(_operation)
    return seeded


def _completed_candidate(
    seeded: _SeededRun, *, tool_call_id: str
) -> ToolFactAcceptCandidate:
    """构造 completed 工具事实候选。

    :param seeded: active Run refs。
    :param tool_call_id: tool call id。
    :returns: accept candidate。
    """

    return ToolFactAcceptCandidate(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        iteration_id="iteration-1",
        tool_call_id=tool_call_id,
        tool_name="lookup",
        tool_schema_digest=sha256_digest_json({"schema": "lookup"}),
        tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
        normalized_arguments_digest=sha256_digest_json({"ticker": "MSFT"}),
        tool_fact_kind=ToolFactKind.COMPLETED,
        outcome_digest=sha256_digest_json({"outcome": tool_call_id}),
        payload_digest=sha256_digest_json({"payload": tool_call_id}),
        payload_ref=None,
        truncation=None,
        duplicate_key=None,
        duplicate_decision=None,
        reuse_prior_event_refs=(),
        policy_decision=ToolPolicyDecision(
            kind=ToolPolicyDecisionKind.ALLOW,
            reason_code=None,
            message=None,
        ),
        tool_idempotency_key=None,
        diagnostic_refs=(),
        accept_idempotency_key=f"accept-{tool_call_id}",
        semantic_input_digest=sha256_digest_json({"semantic": tool_call_id}),
    )


def _reuse_candidate(
    seeded: _SeededRun, *, tool_call_id: str, prior_ref: HostEventRef
) -> ToolFactAcceptCandidate:
    """构造 reuse 工具事实候选。

    :param seeded: active Run refs。
    :param tool_call_id: 当前 tool call id。
    :param prior_ref: prior accepted result ref。
    :returns: accept candidate。
    """

    return ToolFactAcceptCandidate(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        iteration_id="iteration-2",
        tool_call_id=tool_call_id,
        tool_name="lookup",
        tool_schema_digest=sha256_digest_json({"schema": "lookup"}),
        tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
        normalized_arguments_digest=sha256_digest_json({"ticker": "MSFT"}),
        tool_fact_kind=ToolFactKind.REUSE,
        outcome_digest=None,
        payload_digest=None,
        payload_ref=None,
        truncation=None,
        duplicate_key="duplicate-lookup-MSFT",
        duplicate_decision=DuplicateDecisionKind.REUSE,
        reuse_prior_event_refs=(prior_ref,),
        policy_decision=ToolPolicyDecision(
            kind=ToolPolicyDecisionKind.REUSE,
            reason_code="duplicate_reuse",
            message="reuse prior accepted tool result",
        ),
        tool_idempotency_key=None,
        diagnostic_refs=(),
        accept_idempotency_key=f"accept-{tool_call_id}",
        semantic_input_digest=sha256_digest_json({"semantic": tool_call_id}),
    )


def _fact_kind_candidate(
    seeded: _SeededRun,
    *,
    tool_call_id: str,
    fact_kind: ToolFactKind,
    policy_kind: ToolPolicyDecisionKind,
) -> ToolFactAcceptCandidate:
    """构造指定 fact kind 的工具事实候选。

    :param seeded: active Run refs。
    :param tool_call_id: tool call id。
    :param fact_kind: 工具事实类别。
    :param policy_kind: policy decision 类别。
    :returns: accept candidate。
    """

    return ToolFactAcceptCandidate(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        iteration_id="iteration-3",
        tool_call_id=tool_call_id,
        tool_name="lookup",
        tool_schema_digest=sha256_digest_json({"schema": "lookup"}),
        tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
        normalized_arguments_digest=sha256_digest_json({"ticker": tool_call_id}),
        tool_fact_kind=fact_kind,
        outcome_digest=sha256_digest_json({"outcome": tool_call_id}),
        payload_digest=None,
        payload_ref=None,
        truncation=None,
        duplicate_key=None,
        duplicate_decision=None,
        reuse_prior_event_refs=(),
        policy_decision=ToolPolicyDecision(
            kind=policy_kind,
            reason_code=policy_kind.value if policy_kind is not ToolPolicyDecisionKind.ALLOW else None,
            message=policy_kind.value if policy_kind is not ToolPolicyDecisionKind.ALLOW else None,
        ),
        tool_idempotency_key=None,
        diagnostic_refs=(),
        accept_idempotency_key=f"accept-{tool_call_id}",
        semantic_input_digest=sha256_digest_json({"semantic": tool_call_id}),
    )


def _tool_events(transaction_runner: HostTransactionRunner) -> tuple[EventLogRow, ...]:
    """读取所有工具 canonical EventLog rows。

    :param transaction_runner: Host transaction runner。
    :returns: 工具事件 rows。
    """

    def _operation(transaction: HostTransaction) -> tuple[EventLogRow, ...]:
        """读取并过滤工具事件。

        :param transaction: Host transaction。
        :returns: 工具事件 rows。
        """

        rows = EventLogStore().read_events_after(transaction, 0, limit=100)
        return tuple(row for row in rows if row.event_type.startswith("TOOL_"))

    return transaction_runner.run_read(_operation)


def _tool_result_events(
    transaction_runner: HostTransactionRunner,
) -> tuple[EventLogRow, ...]:
    """读取所有 ``TOOL_RESULT_ACCEPTED`` rows。

    :param transaction_runner: Host transaction runner。
    :returns: 工具结果事件 rows。
    """

    return tuple(
        row
        for row in _tool_events(transaction_runner)
        if row.event_type == "TOOL_RESULT_ACCEPTED"
    )
