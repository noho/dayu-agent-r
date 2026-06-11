"""Host ToolRuntime accept barrier 测试。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.api import EnsureSessionRequest, HostPayloadRef
from dayu.host._event_payload import payload_object
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.artifact import LocalArtifactRef
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.payload import (
    PayloadKind,
    read_payload_descriptor,
    write_payload_descriptor_for_artifact,
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
from dayu.host.payload_resolution import event_payload_object
from dayu.host.payload_resolution import tool_call_request_atoms
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
    ToolAcceptCall,
    ToolAcceptDiagnostics,
    ToolAcceptDuplicateGovernance,
    ToolAcceptGovernance,
    ToolAcceptIdentity,
    ToolAcceptIdempotency,
    ToolAcceptRejectReason,
    ToolAcceptResult,
    ToolAcceptRetryPolicy,
    ToolFactAcceptTimedOut,
    ToolFactAcceptCandidate,
    ToolFactAcceptedAck,
    ToolFactKind,
    ToolFactRejectedAck,
    ToolPolicyDecision,
    ToolPolicyDecisionKind,
    ToolTraceDiagnosticRef,
)
from dayu.host.tool_duplicate_governance import DuplicateGovernanceScope
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "tool-accept-test"})
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE = "accepted_evidence_envelope"
_PAYLOAD_FIELD_RAW_TOOL_OUTCOME = "raw_tool_outcome"


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
            candidate.call.normalized_arguments_digest
        )
        assert envelope.tool_query.semantic_input_digest == (
            candidate.idempotency.semantic_input_digest
        )
        candidate_result = _required_result(candidate)
        assert envelope.result_ref.payload_ref is None
        assert envelope.result_ref.payload_digest == candidate_result.payload_digest
        assert envelope.result_ref.outcome_digest == candidate_result.outcome_digest
        assert envelope.result_ref.truncation_applied is False
        assert envelope.source_refs == ()
        assert envelope.locator_refs == ()
        assert payload["raw_tool_outcome"] == candidate_result.raw_tool_outcome
        assert payload["failure_metadata"] is None
        assert "result_preview" not in payload


def test_tool_call_requested_carries_inline_arguments_atom(
    tmp_path: Path,
) -> None:
    """小参数 TOOL_CALL_REQUESTED 内联 accepted arguments atom。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _completed_candidate(seeded, tool_call_id="tool-call-args-inline")
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)
        requested = _tool_requested_events(store.transaction_runner)[0]
        payload = payload_object(requested)
        atoms = store.transaction_runner.run_read(
            lambda transaction: tool_call_request_atoms(transaction, requested)
        )

        assert isinstance(result, ToolFactAcceptedAck)
        assert payload["arguments_storage_kind"] == "inline_json"
        assert payload["arguments_inline_json"] == {
            "arguments": {"ticker": "MSFT"}
        }
        assert payload["arguments_payload_ref"] is None
        assert payload["arguments_payload_digest"] == (
            candidate.call.normalized_arguments_digest
        )
        assert payload["semantic_query_storage_kind"] == "absent"
        assert atoms.arguments_json == {"arguments": {"ticker": "MSFT"}}
        assert atoms.semantic_query_text is None


def test_tool_call_requested_large_arguments_use_payload_descriptor(
    tmp_path: Path,
) -> None:
    """大参数 TOOL_CALL_REQUESTED 使用 tool_call_arguments_json descriptor。"""

    with open_host_durable_store(
        _options(tmp_path, payload_inline_threshold_bytes=4096)
    ) as store:
        seeded = _seed_active_run(store.transaction_runner)
        base = _completed_candidate(seeded, tool_call_id="tool-call-args-large")
        large_arguments: Mapping[str, JsonValue] = {
            "ticker": "MSFT",
            "query": "x" * 8192,
        }
        candidate = replace(
            base,
            call=replace(
                base.call,
                accepted_arguments=large_arguments,
                normalized_arguments_digest=sha256_digest_json(
                    {"arguments": large_arguments}
                ),
            ),
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)
        requested = _tool_requested_events(store.transaction_runner)[0]
        payload = payload_object(requested)
        atoms = store.transaction_runner.run_read(
            lambda transaction: tool_call_request_atoms(transaction, requested)
        )
        descriptor = store.transaction_runner.run_read(
            lambda transaction: read_payload_descriptor(
                transaction,
                cast(str, payload["arguments_payload_ref"]),
            )
        )

        assert isinstance(result, ToolFactAcceptedAck)
        assert payload["arguments_storage_kind"] == "payload_descriptor"
        assert payload["arguments_inline_json"] is None
        assert payload["arguments_payload_digest"] == (
            candidate.call.normalized_arguments_digest
        )
        assert descriptor is not None
        assert descriptor.payload_kind is PayloadKind.SQLITE_PAYLOAD
        assert '"descriptor_kind":"tool_call_arguments_json"' in (
            descriptor.metadata_json
        )
        assert atoms.arguments_json == {"arguments": large_arguments}
        assert canonical_json_dumps(large_arguments) not in requested.payload_json


def test_tool_call_request_atoms_reject_inline_arguments_payload_ref(
    tmp_path: Path,
) -> None:
    """reader 拒绝 inline arguments 同时携带 payload ref 的畸形 atom。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _completed_candidate(
            seeded, tool_call_id="tool-call-args-inline-bad-ref"
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)
        requested = _tool_requested_events(store.transaction_runner)[0]
        malformed_payload = dict(payload_object(requested))
        malformed_payload["arguments_payload_ref"] = "payload:unexpected-arguments"
        malformed_requested = replace(
            requested,
            payload_json=canonical_json_dumps(malformed_payload),
        )

        assert isinstance(result, ToolFactAcceptedAck)
        with pytest.raises(HostDurableError, match="inline tool call arguments"):
            store.transaction_runner.run_read(
                lambda transaction: tool_call_request_atoms(
                    transaction, malformed_requested
                )
            )


def test_tool_accept_call_rejects_arguments_digest_mismatch() -> None:
    """ToolAcceptCall 拒绝 normalized digest 与 accepted arguments 不同源。"""

    with pytest.raises(ValueError, match="accepted canonical arguments"):
        ToolAcceptCall(
            iteration_id="iteration-1",
            tool_call_id="tool-call-args-mismatch",
            tool_name="lookup",
            tool_schema_digest=sha256_digest_json({"schema": "lookup"}),
            tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
            normalized_arguments_digest=sha256_digest_json(
                {"arguments": {"ticker": "MSFT"}}
            ),
            accepted_arguments={"ticker": "AAPL"},
        )


def test_tool_call_requested_semantic_query_inline_and_descriptor(
    tmp_path: Path,
) -> None:
    """semantic query 缺失合法；存在时支持 inline 与 descriptor 两种形态。"""

    with open_host_durable_store(
        _options(tmp_path, payload_inline_threshold_bytes=4096)
    ) as store:
        seeded = _seed_active_run(store.transaction_runner)
        inline_base = _completed_candidate(
            seeded, tool_call_id="tool-call-query-inline"
        )
        descriptor_base = _completed_candidate(
            seeded, tool_call_id="tool-call-query-descriptor"
        )
        inline_candidate = replace(
            inline_base,
            call=replace(inline_base.call, semantic_query_text="lookup MSFT filing"),
        )
        descriptor_query = "readable query " + ("x" * 8192)
        descriptor_candidate = replace(
            descriptor_base,
            call=replace(
                descriptor_base.call,
                semantic_query_text=descriptor_query,
            ),
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        inline_result = accept_port.accept_tool_fact(inline_candidate)
        descriptor_result = accept_port.accept_tool_fact(descriptor_candidate)
        requested_events = _tool_requested_events(store.transaction_runner)
        inline_atoms = store.transaction_runner.run_read(
            lambda transaction: tool_call_request_atoms(
                transaction, requested_events[0]
            )
        )
        descriptor_payload = payload_object(requested_events[1])
        descriptor_atoms = store.transaction_runner.run_read(
            lambda transaction: tool_call_request_atoms(
                transaction, requested_events[1]
            )
        )

        assert isinstance(inline_result, ToolFactAcceptedAck)
        assert isinstance(descriptor_result, ToolFactAcceptedAck)
        assert inline_atoms.semantic_query_text == "lookup MSFT filing"
        assert payload_object(requested_events[0])["semantic_query_storage_kind"] == (
            "inline_text"
        )
        assert descriptor_payload["semantic_query_storage_kind"] == (
            "payload_descriptor"
        )
        assert descriptor_payload["semantic_query_text"] is None
        assert descriptor_atoms.semantic_query_text == descriptor_query
        assert descriptor_query not in requested_events[1].payload_json


def test_tool_call_request_atoms_reject_inline_semantic_query_payload_ref(
    tmp_path: Path,
) -> None:
    """reader 拒绝 inline semantic query 同时携带 payload ref 的畸形 atom。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        base = _completed_candidate(
            seeded, tool_call_id="tool-call-query-inline-bad-ref"
        )
        candidate = replace(
            base,
            call=replace(base.call, semantic_query_text="lookup MSFT filing"),
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)
        requested = _tool_requested_events(store.transaction_runner)[0]
        malformed_payload = dict(payload_object(requested))
        malformed_payload["semantic_query_payload_ref"] = (
            "payload:unexpected-semantic-query"
        )
        malformed_requested = replace(
            requested,
            payload_json=canonical_json_dumps(malformed_payload),
        )

        assert isinstance(result, ToolFactAcceptedAck)
        with pytest.raises(HostDurableError, match="inline semantic query"):
            store.transaction_runner.run_read(
                lambda transaction: tool_call_request_atoms(
                    transaction, malformed_requested
                )
            )


def test_tool_result_accepted_large_payload_uses_sqlite_payload_descriptor(
    tmp_path: Path,
) -> None:
    """大工具结果冷热分离，EventLog inline 只保留热元数据与 descriptor ref。"""

    with open_host_durable_store(
        _options(tmp_path, payload_inline_threshold_bytes=4096)
    ) as store:
        seeded = _seed_active_run(store.transaction_runner)
        base = _completed_candidate(seeded, tool_call_id="tool-call-large-payload")
        candidate = replace(
            base,
            result=replace(
                _required_result(base),
                raw_tool_outcome=_large_raw_tool_outcome(
                    "tool-call-large-payload"
                ),
                outcome_digest=sha256_digest_json(
                    {"outcome": "tool-call-large-payload"}
                ),
                payload_digest=sha256_digest_json(
                    {"payload": "tool-call-large-payload"}
                ),
            ),
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)
        result_rows = _tool_result_events(store.transaction_runner)

        assert isinstance(result, ToolFactAcceptedAck)
        assert result.tool_result_event_ref is not None
        assert result.result_payload_ref is not None
        assert len(result_rows) == 1
        row = result_rows[0]
        assert row.payload_ref == result.result_payload_ref.payload_ref
        assert row.payload_digest == result.result_payload_ref.payload_digest
        inline_payload = payload_object(row)
        assert _PAYLOAD_FIELD_RAW_TOOL_OUTCOME not in inline_payload
        assert inline_payload["payload_ref"] == {
            "payload_ref": row.payload_ref,
            "payload_digest": row.payload_digest,
        }

        cold_payload = _read_event_payload(store.transaction_runner, row)
        envelope = accepted_evidence_envelope_from_json_value(
            cold_payload[_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE]
        )
        assert (
            cold_payload[_PAYLOAD_FIELD_RAW_TOOL_OUTCOME]
            == _required_result(candidate).raw_tool_outcome
        )
        assert envelope.result_ref.payload_ref == row.payload_ref
        assert envelope.result_ref.payload_digest is None
        assert envelope.result_ref.outcome_digest == _required_result(
            candidate
        ).outcome_digest


def test_accept_rejects_missing_payload_descriptor_before_writing_events(
    tmp_path: Path,
) -> None:
    """accept barrier 在写 accepted events 前拒绝缺失 payload descriptor。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        payload_digest = sha256_digest_json({"payload": "missing-descriptor"})
        base = _completed_candidate(seeded, tool_call_id="tool-call-missing-payload")
        candidate = replace(
            base,
            result=replace(
                _required_result(base),
                payload_digest=payload_digest,
                payload_ref=HostPayloadRef(
                    payload_ref="payload:missing-descriptor",
                    payload_digest=payload_digest,
                ),
            ),
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)

        assert isinstance(result, ToolFactRejectedAck)
        assert result.reason_code is ToolAcceptRejectReason.PAYLOAD_REFERENCE_INVALID
        assert _tool_events(store.transaction_runner) == ()


def test_accept_rejects_payload_descriptor_digest_mismatch(
    tmp_path: Path,
) -> None:
    """accept barrier 拒绝 descriptor 存在但 digest 不匹配的 payload_ref。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        payload_ref = "payload:digest-mismatch"
        stored_digest = sha256_digest_json({"payload": "stored"})
        candidate_digest = sha256_digest_json({"payload": "candidate"})
        store.transaction_runner.run_write(
            partial(
                _write_artifact_payload_descriptor,
                payload_ref=payload_ref,
                payload_digest=stored_digest,
            )
        )
        base = _completed_candidate(seeded, tool_call_id="tool-call-payload-mismatch")
        candidate = replace(
            base,
            result=replace(
                _required_result(base),
                payload_digest=candidate_digest,
                payload_ref=HostPayloadRef(
                    payload_ref=payload_ref,
                    payload_digest=candidate_digest,
                ),
            ),
        )
        accept_port = DefaultHostToolFactAcceptPort(
            transaction_runner=store.transaction_runner
        )

        result = accept_port.accept_tool_fact(candidate)

        assert isinstance(result, ToolFactRejectedAck)
        assert result.reason_code is ToolAcceptRejectReason.PAYLOAD_REFERENCE_INVALID
        assert _tool_events(store.transaction_runner) == ()


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
        assert snapshot.snapshot.evidence_fact_memory.evidence_backed_facts == ()
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
            idempotency=replace(
                candidate.idempotency,
                semantic_input_digest=sha256_digest_json({"semantic": "changed"}),
            ),
            result=replace(
                _required_result(candidate),
                outcome_digest=sha256_digest_json({"outcome": "changed"}),
            ),
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
            identity=replace(base.identity, attempt_id="attempt-missing"),
            idempotency=replace(
                base.idempotency,
                accept_idempotency_key="accept-missing",
            ),
        )
        stale_execution = replace(
            base,
            identity=replace(base.identity, execution_id="execution-stale"),
            call=replace(base.call, tool_call_id="tool-call-stale"),
            idempotency=replace(
                base.idempotency,
                accept_idempotency_key="accept-stale",
            ),
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
        assert _required_duplicate(reuse).reuse_prior_event_refs == (
            first.tool_result_event_ref,
        )
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
        governed_payload = payload_object(tool_events[-1])
        duplicate_scope = governed_payload["duplicate_scope"]
        assert isinstance(duplicate_scope, Mapping)
        assert duplicate_scope["kind"] == "attempt"
        assert duplicate_scope["attempt_id"] == reuse.identity.attempt_id
        assert governed_payload["reuse_prior_event_refs"] == [
            {
                "event_id": first.tool_result_event_ref.event_id,
                "event_sequence": first.tool_result_event_ref.event_sequence,
            }
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
            governance=ToolAcceptGovernance(
                policy_decision=ToolPolicyDecision(
                    kind=ToolPolicyDecisionKind.ALLOW,
                    reason_code=None,
                    message=None,
                ),
                tool_idempotency_key=None,
                duplicate=ToolAcceptDuplicateGovernance(
                    duplicate_key="duplicate-lookup-MSFT",
                    duplicate_decision=DuplicateDecisionKind.ALLOW,
                    duplicate_scope=DuplicateGovernanceScope(
                        kind="attempt", attempt_id=seeded.attempt_id
                    ),
                    duplicate_decision_message="本次重复工具调用已允许执行。",
                    reuse_prior_event_refs=(),
                ),
            ),
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
        assert payloads[0]["tool_timing"] == _missing_tool_timing()
        assert payloads[1]["tool_timing"] == _missing_tool_timing()
        assert payloads[2]["tool_timing"] == _missing_tool_timing()
        assert payloads[0]["failure_metadata"] == _failure_metadata_for_fact_kind(
            fact_kind=ToolFactKind.FAILED,
            policy_kind=ToolPolicyDecisionKind.ALLOW,
        )
        assert payloads[1]["failure_metadata"] == _failure_metadata_for_fact_kind(
            fact_kind=ToolFactKind.CANCELLED,
            policy_kind=ToolPolicyDecisionKind.ALLOW,
        )
        assert payloads[2]["failure_metadata"] == _failure_metadata_for_fact_kind(
            fact_kind=ToolFactKind.GOVERNED_ERROR,
            policy_kind=ToolPolicyDecisionKind.GOVERNED_ERROR,
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
                governance=ToolAcceptGovernance(
                    policy_decision=ToolPolicyDecision(
                        kind=ToolPolicyDecisionKind.ALLOW,
                        reason_code=None,
                        message=None,
                    ),
                    tool_idempotency_key=None,
                    duplicate=ToolAcceptDuplicateGovernance(
                        duplicate_key=None,
                        duplicate_decision=DuplicateDecisionKind.ALLOW,
                        duplicate_scope=DuplicateGovernanceScope(
                            kind="attempt", attempt_id=seeded.attempt_id
                        ),
                        duplicate_decision_message="本次重复工具调用已允许执行。",
                        reuse_prior_event_refs=(accepted.tool_result_event_ref,),
                    ),
                ),
            )


def test_lost_tool_fact_kind_fails_fast_as_unsupported() -> None:
    """LOST 工具事实类别在 accept candidate 构造期明确 fail-fast。

    :returns: ``None``。
    :raises AssertionError: LOST 未按 unsupported fact kind 拒绝时抛出。
    """

    seeded = _SeededRun(
        session_id="session-tool-accept",
        run_id="run-tool-accept",
        attempt_id="attempt-tool-accept",
        execution_id="execution-tool-accept",
        dispatch_record_id="dispatch-tool-accept",
    )
    base = _completed_candidate(seeded, tool_call_id="tool-call-lost")

    with pytest.raises(ValueError, match="unsupported tool_fact_kind"):
        replace(base, tool_fact_kind=ToolFactKind.LOST)


def test_tool_accept_identity_rejects_empty_fields() -> None:
    """ToolAcceptIdentity 直接拒绝任一空身份字段。

    :returns: ``None``。
    :raises AssertionError: 空身份字段未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="session_id"):
        ToolAcceptIdentity(
            session_id="",
            run_id="run-tool-accept",
            attempt_id="attempt-tool-accept",
            execution_id="execution-tool-accept",
        )
    with pytest.raises(ValueError, match="run_id"):
        ToolAcceptIdentity(
            session_id="session-tool-accept",
            run_id="",
            attempt_id="attempt-tool-accept",
            execution_id="execution-tool-accept",
        )
    with pytest.raises(ValueError, match="attempt_id"):
        ToolAcceptIdentity(
            session_id="session-tool-accept",
            run_id="run-tool-accept",
            attempt_id="",
            execution_id="execution-tool-accept",
        )
    with pytest.raises(ValueError, match="execution_id"):
        ToolAcceptIdentity(
            session_id="session-tool-accept",
            run_id="run-tool-accept",
            attempt_id="attempt-tool-accept",
            execution_id="",
        )


def test_tool_accept_call_rejects_invalid_digest() -> None:
    """ToolAcceptCall 直接拒绝非法 digest 字段。

    :returns: ``None``。
    :raises AssertionError: 非法 digest 未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="tool_schema_digest"):
        ToolAcceptCall(
            iteration_id="iteration-1",
            tool_call_id="tool-call-invalid-digest",
            tool_name="lookup",
            tool_schema_digest="not-a-sha256-digest",
            tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
            normalized_arguments_digest=sha256_digest_json(
                {"arguments": {"ticker": "MSFT"}}
            ),
            accepted_arguments={"ticker": "MSFT"},
        )


def test_tool_accept_result_rejects_payload_ref_digest_mismatch() -> None:
    """ToolAcceptResult 直接拒绝 payload_digest 与 payload_ref digest 不一致。

    :returns: ``None``。
    :raises AssertionError: payload digest 不一致未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="payload_digest must match"):
        ToolAcceptResult(
            outcome_digest=sha256_digest_json({"outcome": "payload-mismatch"}),
            payload_digest=sha256_digest_json({"payload": "candidate"}),
            payload_ref=HostPayloadRef(
                payload_ref="payload:result-mismatch",
                payload_digest=sha256_digest_json({"payload": "ref"}),
            ),
            truncation=None,
            raw_tool_outcome=_raw_tool_outcome("tool-call-payload-mismatch"),
            tool_timing=_missing_tool_timing(),
        )


def test_tool_accept_duplicate_governance_rejects_invalid_fields() -> None:
    """ToolAcceptDuplicateGovernance 直接拒绝缺失字段与非法 prior ref。

    :returns: ``None``。
    :raises AssertionError: duplicate governance 非法字段未被拒绝时抛出。
    """

    scope = DuplicateGovernanceScope(kind="attempt", attempt_id="attempt-tool-accept")

    with pytest.raises(ValueError, match="duplicate_scope"):
        ToolAcceptDuplicateGovernance(
            duplicate_key=None,
            duplicate_decision=DuplicateDecisionKind.ALLOW,
            duplicate_scope=None,
            duplicate_decision_message="本次重复工具调用已允许执行。",
            reuse_prior_event_refs=(),
        )
    with pytest.raises(ValueError, match="duplicate_decision_message"):
        ToolAcceptDuplicateGovernance(
            duplicate_key=None,
            duplicate_decision=DuplicateDecisionKind.ALLOW,
            duplicate_scope=scope,
            duplicate_decision_message=None,
            reuse_prior_event_refs=(),
        )
    with pytest.raises(ValueError, match="reuse_prior_event_refs"):
        ToolAcceptDuplicateGovernance(
            duplicate_key=None,
            duplicate_decision=DuplicateDecisionKind.ALLOW,
            duplicate_scope=scope,
            duplicate_decision_message="本次重复工具调用已允许执行。",
            reuse_prior_event_refs=(cast(HostEventRef, "bad-prior-ref"),),
        )


def test_tool_accept_governance_rejects_non_policy_decision() -> None:
    """ToolAcceptGovernance 直接拒绝非 ToolPolicyDecision。

    :returns: ``None``。
    :raises AssertionError: 非 ToolPolicyDecision 未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="policy_decision"):
        ToolAcceptGovernance(
            policy_decision=cast(ToolPolicyDecision, "bad-policy-decision"),
            tool_idempotency_key=None,
            duplicate=None,
        )


def test_tool_accept_idempotency_rejects_invalid_semantic_digest() -> None:
    """ToolAcceptIdempotency 直接拒绝非法 semantic input digest。

    :returns: ``None``。
    :raises AssertionError: 非法 semantic input digest 未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="semantic_input_digest"):
        ToolAcceptIdempotency(
            accept_idempotency_key="accept-invalid-semantic",
            semantic_input_digest="not-a-sha256-digest",
        )


def test_tool_accept_diagnostics_rejects_non_diagnostic_ref() -> None:
    """ToolAcceptDiagnostics 直接拒绝非 ToolTraceDiagnosticRef 引用。

    :returns: ``None``。
    :raises AssertionError: 非 ToolTraceDiagnosticRef 未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="diagnostic_refs"):
        ToolAcceptDiagnostics(
            diagnostic_refs=(cast(ToolTraceDiagnosticRef, "bad-diagnostic-ref"),)
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


def _options(
    tmp_path: Path, *, payload_inline_threshold_bytes: int = 65536
) -> HostDurableStoreOptions:
    """构造测试 durable store options。

    :param tmp_path: pytest 临时目录。
    :param payload_inline_threshold_bytes: payload inline 阈值。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts",
            payload_inline_threshold_bytes=payload_inline_threshold_bytes,
        ),
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


def _write_artifact_payload_descriptor(
    transaction: HostTransaction, *, payload_ref: str, payload_digest: str
) -> None:
    """写入测试用 artifact payload descriptor。

    :param transaction: Host transaction。
    :param payload_ref: payload descriptor ref。
    :param payload_digest: descriptor 记录的 payload digest。
    :returns: ``None``。
    """

    write_payload_descriptor_for_artifact(
        transaction,
        payload_ref,
        LocalArtifactRef(
            artifact_relative_path="tool/digest-mismatch.json",
            artifact_digest=payload_digest,
            artifact_size_bytes=128,
        ),
        "application/json",
        {},
    )


def _completed_candidate(
    seeded: _SeededRun, *, tool_call_id: str
) -> ToolFactAcceptCandidate:
    """构造 completed 工具事实候选。

    :param seeded: active Run refs。
    :param tool_call_id: tool call id。
    :returns: accept candidate。
    """

    return ToolFactAcceptCandidate(
        identity=_candidate_identity(seeded),
        call=_candidate_call(tool_call_id, iteration_id="iteration-1"),
        tool_fact_kind=ToolFactKind.COMPLETED,
        result=ToolAcceptResult(
            outcome_digest=sha256_digest_json({"outcome": tool_call_id}),
            payload_digest=sha256_digest_json({"payload": tool_call_id}),
            payload_ref=None,
            truncation=None,
            raw_tool_outcome=_raw_tool_outcome(tool_call_id),
            tool_timing=_missing_tool_timing(),
        ),
        governance=_allow_governance(duplicate=None),
        idempotency=_candidate_idempotency(tool_call_id),
        diagnostics=ToolAcceptDiagnostics(diagnostic_refs=()),
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
        identity=_candidate_identity(seeded),
        call=_candidate_call(tool_call_id, iteration_id="iteration-2"),
        tool_fact_kind=ToolFactKind.REUSE,
        result=None,
        governance=ToolAcceptGovernance(
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.REUSE,
                reason_code="duplicate_reuse",
                message="请直接使用上一次工具结果继续推理，不要重复请求相同证据。",
            ),
            tool_idempotency_key=None,
            duplicate=ToolAcceptDuplicateGovernance(
                duplicate_key="duplicate-lookup-MSFT",
                duplicate_decision=DuplicateDecisionKind.REUSE,
                duplicate_scope=DuplicateGovernanceScope(
                    kind="attempt", attempt_id=seeded.attempt_id
                ),
                duplicate_decision_message=(
                    "请直接使用上一次工具结果继续推理，不要重复请求相同证据。"
                ),
                reuse_prior_event_refs=(prior_ref,),
            ),
        ),
        idempotency=_candidate_idempotency(tool_call_id),
        diagnostics=ToolAcceptDiagnostics(diagnostic_refs=()),
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
        identity=_candidate_identity(seeded),
        call=ToolAcceptCall(
            iteration_id="iteration-3",
            tool_call_id=tool_call_id,
            tool_name="lookup",
            tool_schema_digest=sha256_digest_json({"schema": "lookup"}),
            tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
            normalized_arguments_digest=sha256_digest_json(
                {"arguments": {"ticker": tool_call_id}}
            ),
            accepted_arguments={"ticker": tool_call_id},
        ),
        tool_fact_kind=fact_kind,
        result=ToolAcceptResult(
            outcome_digest=sha256_digest_json({"outcome": tool_call_id}),
            payload_digest=None,
            payload_ref=None,
            truncation=None,
            raw_tool_outcome=_raw_tool_outcome(tool_call_id),
            tool_timing=_missing_tool_timing(),
            failure_metadata=_failure_metadata_for_fact_kind(
                fact_kind=fact_kind,
                policy_kind=policy_kind,
            ),
        ),
        governance=ToolAcceptGovernance(
            policy_decision=ToolPolicyDecision(
                kind=policy_kind,
                reason_code=(
                    policy_kind.value
                    if policy_kind is not ToolPolicyDecisionKind.ALLOW
                    else None
                ),
                message=(
                    policy_kind.value
                    if policy_kind is not ToolPolicyDecisionKind.ALLOW
                    else None
                ),
            ),
            tool_idempotency_key=None,
            duplicate=None,
        ),
        idempotency=_candidate_idempotency(tool_call_id),
        diagnostics=ToolAcceptDiagnostics(diagnostic_refs=()),
    )


def _candidate_identity(seeded: _SeededRun) -> ToolAcceptIdentity:
    """构造测试 candidate identity 子结构。

    :param seeded: active Run refs。
    :returns: candidate identity。
    """

    return ToolAcceptIdentity(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
    )


def _candidate_call(tool_call_id: str, *, iteration_id: str) -> ToolAcceptCall:
    """构造测试 candidate call 子结构。

    :param tool_call_id: tool call id。
    :param iteration_id: iteration id。
    :returns: candidate call。
    """

    return ToolAcceptCall(
        iteration_id=iteration_id,
        tool_call_id=tool_call_id,
        tool_name="lookup",
        tool_schema_digest=sha256_digest_json({"schema": "lookup"}),
        tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
        normalized_arguments_digest=sha256_digest_json(
            {"arguments": {"ticker": "MSFT"}}
        ),
        accepted_arguments={"ticker": "MSFT"},
    )


def _allow_governance(
    *, duplicate: ToolAcceptDuplicateGovernance | None
) -> ToolAcceptGovernance:
    """构造 allow policy governance 子结构。

    :param duplicate: 可选 duplicate governance。
    :returns: candidate governance。
    """

    return ToolAcceptGovernance(
        policy_decision=ToolPolicyDecision(
            kind=ToolPolicyDecisionKind.ALLOW,
            reason_code=None,
            message=None,
        ),
        tool_idempotency_key=None,
        duplicate=duplicate,
    )


def _candidate_idempotency(tool_call_id: str) -> ToolAcceptIdempotency:
    """构造测试 candidate idempotency 子结构。

    :param tool_call_id: tool call id。
    :returns: candidate idempotency。
    """

    return ToolAcceptIdempotency(
        accept_idempotency_key=f"accept-{tool_call_id}",
        semantic_input_digest=sha256_digest_json({"semantic": tool_call_id}),
    )


def _required_result(candidate: ToolFactAcceptCandidate) -> ToolAcceptResult:
    """读取必须存在的 result 子结构。

    :param candidate: 工具事实候选。
    :returns: result 子结构。
    :raises AssertionError: candidate 未携带 result 时抛出。
    """

    assert candidate.result is not None
    return candidate.result


def _required_duplicate(
    candidate: ToolFactAcceptCandidate,
) -> ToolAcceptDuplicateGovernance:
    """读取必须存在的 duplicate governance 子结构。

    :param candidate: 工具事实候选。
    :returns: duplicate governance 子结构。
    :raises AssertionError: candidate 未携带 duplicate governance 时抛出。
    """

    assert candidate.governance.duplicate is not None
    return candidate.governance.duplicate


def _failure_metadata_for_fact_kind(
    *, fact_kind: ToolFactKind, policy_kind: ToolPolicyDecisionKind
) -> Mapping[str, JsonValue] | None:
    """构造测试候选使用的 failure metadata。

    :param fact_kind: 工具事实类别。
    :param policy_kind: policy decision 类别。
    :returns: failure metadata JSON object；成功时为 ``None``。
    """

    if fact_kind is ToolFactKind.FAILED:
        return {
            "schema_version": 1,
            "signal_source": "TOOL_RESULT_ACCEPTED",
            "failure_kind": "tool_failed",
            "error_code": "lookup_failed",
            "repair_hint": "retry lookup",
            "repair_hint_truncated": False,
            "repair_hint_sha256": _text_sha256("retry lookup"),
            "diagnostic_refs": [],
        }
    if fact_kind is ToolFactKind.CANCELLED:
        return {
            "schema_version": 1,
            "signal_source": "TOOL_RESULT_ACCEPTED",
            "failure_kind": "tool_cancelled",
            "cancel_reason": "host_cancelled",
            "cancel_message": "cancelled by host",
            "cancel_message_truncated": False,
            "cancel_message_sha256": _text_sha256("cancelled by host"),
            "cancel_hint": None,
            "cancel_hint_truncated": False,
            "cancel_hint_sha256": None,
            "diagnostic_refs": [],
        }
    if fact_kind is ToolFactKind.GOVERNED_ERROR:
        return {
            "schema_version": 1,
            "signal_source": "TOOL_RESULT_ACCEPTED",
            "failure_kind": "policy_blocked",
            "policy_decision_kind": policy_kind.value,
            "policy_block_reason": policy_kind.value,
            "diagnostic_refs": [],
        }
    return None


def _raw_tool_outcome(tool_call_id: str) -> JsonValue:
    """构造测试用 raw tool outcome。

    :param tool_call_id: 工具调用 id。
    :returns: raw outcome JSON。
    """

    return {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": {"tool_call_id": tool_call_id},
            "meta": None,
        },
    }


def _text_sha256(value: str) -> str:
    """计算文本 UTF-8 sha256 digest。

    :param value: 原始文本。
    :returns: ``sha256:`` 前缀 digest。
    """

    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _missing_tool_timing() -> Mapping[str, JsonValue]:
    """构造缺失工具结果 meta 的 timing signal。

    :returns: tool_timing JSON object。
    """

    return {
        "schema_version": 1,
        "status": "missing_tool_result_meta",
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "duration_source": None,
    }


def _large_raw_tool_outcome(tool_call_id: str) -> JsonValue:
    """构造超过 inline 阈值的 raw tool outcome。

    :param tool_call_id: 工具调用 id。
    :returns: 大 raw outcome JSON。
    """

    return {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": {
                "tool_call_id": tool_call_id,
                "large_text": "X" * 10000,
            },
            "meta": None,
        },
    }


def _read_event_payload(
    transaction_runner: HostTransactionRunner, row: EventLogRow
) -> Mapping[str, JsonValue]:
    """读取 EventLog row 的完整 payload，必要时跟随 descriptor。

    :param transaction_runner: Host transaction runner。
    :param row: EventLog row。
    :returns: 完整 payload JSON object。
    """

    def _operation(transaction: HostTransaction) -> Mapping[str, JsonValue]:
        """读取完整 payload。

        :param transaction: Host transaction。
        :returns: 完整 payload JSON object。
        """

        return event_payload_object(
            transaction,
            row,
            payload_label="TOOL_RESULT_ACCEPTED",
        )

    return transaction_runner.run_read(_operation)


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


def _tool_requested_events(
    transaction_runner: HostTransactionRunner,
) -> tuple[EventLogRow, ...]:
    """读取所有 ``TOOL_CALL_REQUESTED`` rows。

    :param transaction_runner: Host transaction runner。
    :returns: 工具请求事件 rows。
    """

    return tuple(
        row
        for row in _tool_events(transaction_runner)
        if row.event_type == "TOOL_CALL_REQUESTED"
    )
