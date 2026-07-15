"""Host ToolAwaiting accept path 测试。"""

from __future__ import annotations

import json
import inspect
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import dayu.host.waiting as waiting_module

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.host.api import AttemptStatus, EnsureSessionRequest, RunStatus, WaitAdapterKey
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendResult,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.idempotency import (
    IdempotencyScope,
    IdempotencyScopeKind,
    IdempotencyStore,
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
    AttemptRow,
    RunRow,
    RunStartReason,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    WaitSnapshotRef,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_run_by_id,
    read_wait_record_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.payload_resolution import tool_call_request_atoms
from dayu.host.wait_adapter import (
    WaitAdapterBinding,
    WaitExternalJobRefSource,
)
from dayu.host.waiting import (
    DefaultHostToolAwaitingAcceptPort,
    HostToolAwaitingAcceptPort,
    ToolAwaitingAcceptCandidate,
    ToolAwaitingAcceptedAck,
    ToolAwaitingRejectedAck,
)

_NOW = datetime(2026, 5, 16, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "awaiting-accept-test"})


def test_awaiting_accept_port_is_abstract() -> None:
    """awaiting accept port 必须是抽象端口，不能直接实例化。"""

    assert inspect.isabstract(HostToolAwaitingAcceptPort)


def test_awaiting_accept_creates_wait_record_and_waiting_state(
    tmp_path: Path,
) -> None:
    """awaiting accept 原子写入四类事实、wait record 与 WAITING/SUSPENDED 状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _awaiting_candidate(seeded)
        accept_port = DefaultHostToolAwaitingAcceptPort(transaction_runner=store.transaction_runner)

        result = accept_port.accept_tool_awaiting(candidate)

        assert isinstance(result, ToolAwaitingAcceptedAck)
        assert [ref.event_id for ref in result.accepted_event_refs] == [
            f"event-tool-call-requested-awaiting-{candidate.semantic_input_digest.removeprefix('sha256:')}",
            f"event-tool-awaiting-{candidate.semantic_input_digest.removeprefix('sha256:')}",
            f"event-run-waiting-{candidate.semantic_input_digest.removeprefix('sha256:')}",
            f"event-attempt-suspended-{candidate.semantic_input_digest.removeprefix('sha256:')}",
        ]
        run, attempt, wait_record, events = _read_state(store.transaction_runner, candidate)
        assert run is not None
        assert run.status is RunStatus.WAITING
        assert attempt is not None
        assert attempt.status is AttemptStatus.SUSPENDED
        assert wait_record is not None
        assert wait_record.status is WaitRecordStatus.WAITING
        assert wait_record.external_job_ref is not None
        assert wait_record.external_job_ref.external_job_id == "external-job-1"
        assert [event.event_type for event in events] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_AWAITING",
            "RUN_WAITING",
            "ATTEMPT_SUSPENDED",
        ]
        assert all(event.event_class is EventClass.CANONICAL_FACT for event in events)


def test_awaiting_accept_persists_complete_snapshot_ref(tmp_path: Path) -> None:
    """awaiting accept 持久化完整 snapshot ref。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        snapshot_ref = WaitSnapshotRef(
            snapshot_id="fins-observation-start-test",
            captured_at=_NOW,
            snapshot_digest=sha256_digest_json(
                {
                    "captured_at": format_utc_timestamp(_NOW),
                    "snapshot_id": "fins-observation-start-test",
                }
            ),
        )
        candidate = replace(_awaiting_candidate(seeded), snapshot_ref=snapshot_ref)
        accept_port = DefaultHostToolAwaitingAcceptPort(transaction_runner=store.transaction_runner)

        result = accept_port.accept_tool_awaiting(candidate)

        assert isinstance(result, ToolAwaitingAcceptedAck)
        _, _, wait_record, _ = _read_state(store.transaction_runner, candidate)
        assert wait_record is not None
        assert wait_record.snapshot_ref == snapshot_ref


def test_awaiting_accept_same_key_replays_existing_ack_without_duplicate_events(
    tmp_path: Path,
) -> None:
    """同 accept key + 同 semantic digest 重放既有 awaiting ack。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _awaiting_candidate(seeded)
        accept_port = DefaultHostToolAwaitingAcceptPort(transaction_runner=store.transaction_runner)

        first = accept_port.accept_tool_awaiting(candidate)
        before = _awaiting_events(store.transaction_runner)
        second = accept_port.accept_tool_awaiting(candidate)
        after = _awaiting_events(store.transaction_runner)

        assert isinstance(first, ToolAwaitingAcceptedAck)
        assert isinstance(second, ToolAwaitingAcceptedAck)
        assert second.accepted_event_refs == first.accepted_event_refs
        assert after == before


def test_awaiting_accept_same_key_different_digest_rejects_without_new_facts(
    tmp_path: Path,
) -> None:
    """同 accept key + 不同 semantic digest 返回 rejected ack 且不追加事实。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _awaiting_candidate(seeded)
        conflict = replace(
            candidate,
            semantic_input_digest=sha256_digest_json({"semantic": "changed"}),
        )
        accept_port = DefaultHostToolAwaitingAcceptPort(transaction_runner=store.transaction_runner)

        first = accept_port.accept_tool_awaiting(candidate)
        before = _awaiting_events(store.transaction_runner)
        second = accept_port.accept_tool_awaiting(conflict)
        after = _awaiting_events(store.transaction_runner)

        assert isinstance(first, ToolAwaitingAcceptedAck)
        assert isinstance(second, ToolAwaitingRejectedAck)
        assert second.reason_code.value == "idempotency_conflict"
        assert after == before


def test_awaiting_accept_candidate_rejects_non_hex_digest(
    tmp_path: Path,
) -> None:
    """awaiting accept candidate 拒绝非十六进制 sha256 digest。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _awaiting_candidate(seeded)

        with pytest.raises(ValueError, match="tool_schema_digest must be sha256 digest"):
            replace(
                candidate,
                tool_schema_digest="sha256:" + "g" * 64,
            )


def test_awaiting_accept_stale_execution_rejects_without_wait_record(
    tmp_path: Path,
) -> None:
    """execution_id 不匹配时 awaiting accept 返回 stale_execution 且不写 wait record。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = replace(
            _awaiting_candidate(seeded),
            execution_id="execution-stale",
            accept_idempotency_key="tool-await-stale",
            semantic_input_digest=sha256_digest_json({"semantic": "stale"}),
        )
        accept_port = DefaultHostToolAwaitingAcceptPort(transaction_runner=store.transaction_runner)

        result = accept_port.accept_tool_awaiting(candidate)
        _, _, wait_record, events = _read_state(store.transaction_runner, candidate)

        assert isinstance(result, ToolAwaitingRejectedAck)
        assert result.reason_code.value == "stale_execution"
        assert wait_record is None
        assert events == ()


def test_awaiting_accept_persists_exact_shared_request_atom_and_governance_link(
    tmp_path: Path,
) -> None:
    """awaiting 保存 exact request atom，治理事实只持有真实 row link。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accepted_arguments: dict[str, JsonValue] = {
            "file_path": "/research/input/annual-report.pdf",
            "scope_token": "scope-business-value",
            "nested": {"query": "business query"},
        }
        normalized_arguments_digest = sha256_digest_json(
            {"arguments": accepted_arguments}
        )
        tool_identity_digest = sha256_digest_json(
            {"identity": "awaiting-owner-sentinel"}
        )
        candidate = replace(
            _awaiting_candidate(seeded),
            normalized_arguments_digest=normalized_arguments_digest,
            accepted_arguments=accepted_arguments,
            tool_identity_digest=tool_identity_digest,
        )
        accept_port = DefaultHostToolAwaitingAcceptPort(transaction_runner=store.transaction_runner)

        result = accept_port.accept_tool_awaiting(candidate)

        assert isinstance(result, ToolAwaitingAcceptedAck)
        events = _awaiting_events(store.transaction_runner)
        tool_call_requested = next(
            event for event in events if event.event_type == "TOOL_CALL_REQUESTED"
        )
        request_payload = json.loads(tool_call_requested.payload_json)
        assert isinstance(request_payload, dict)
        assert set(request_payload) == {
            "session_id",
            "run_id",
            "attempt_id",
            "execution_id",
            "iteration_id",
            "tool_call_id",
            "tool_name",
            "tool_schema_digest",
            "tool_identity_digest",
            "normalized_arguments_digest",
            "arguments_json_size_bytes",
            "arguments_storage_kind",
            "arguments_inline_json",
            "arguments_payload_ref",
            "arguments_payload_digest",
            "tool_fact_kind",
            "accept_idempotency_key",
            "semantic_input_digest",
            "semantic_query_storage_kind",
            "semantic_query_text",
            "semantic_query_payload_ref",
            "semantic_query_digest",
        }
        assert request_payload["arguments_inline_json"] == {
            "arguments": accepted_arguments
        }
        assert request_payload["arguments_payload_digest"] == normalized_arguments_digest
        assert request_payload["tool_identity_digest"] == tool_identity_digest
        assert request_payload["semantic_query_storage_kind"] == "absent"
        assert request_payload["semantic_query_text"] is None
        assert request_payload["semantic_query_payload_ref"] is None
        assert request_payload["semantic_query_digest"] is None
        assert tool_call_requested.actor == "host.tool_runtime"
        assert tool_call_requested.source == "host.tool_runtime.awaiting_accept"

        tool_awaiting = next(event for event in events if event.event_type == "TOOL_AWAITING")
        payload = json.loads(tool_awaiting.payload_json)
        assert isinstance(payload, dict)
        assert set(payload) == {
            "session_id",
            "run_id",
            "attempt_id",
            "execution_id",
            "iteration_id",
            "wait_id",
            "tool_call_id",
            "tool_name",
            "tool_call_requested_event_ref",
            "await_spec",
            "adapter_key",
            "resume_policy",
            "snapshot_ref",
            "external_job_ref",
            "accept_idempotency_key",
            "semantic_input_digest",
        }
        assert payload["tool_call_requested_event_ref"] == {
            "event_id": tool_call_requested.event_id,
            "event_sequence": tool_call_requested.event_sequence,
        }
        assert "accepted_arguments" not in payload
        assert "accepted_arguments_source_digest" not in payload
        assert "normalized_arguments_digest" not in payload
        assert all(not key.startswith("arguments_") for key in payload)

        atoms = store.transaction_runner.run_read(
            lambda transaction: tool_call_request_atoms(
                transaction, tool_call_requested
            )
        )
        assert atoms.arguments_json == {"arguments": accepted_arguments}
        assert atoms.normalized_arguments_digest == normalized_arguments_digest
        assert atoms.arguments_payload_digest == normalized_arguments_digest


def test_awaiting_accept_large_arguments_use_shared_descriptor_writer(
    tmp_path: Path,
) -> None:
    """awaiting 大参数走共享 descriptor，hot request 与治理事实均不复制正文。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accepted_arguments: dict[str, JsonValue] = {
            "file_path": "/research/input/large.pdf",
            "content": "x" * 200_000,
        }
        digest = sha256_digest_json({"arguments": accepted_arguments})
        candidate = replace(
            _awaiting_candidate(seeded),
            accepted_arguments=accepted_arguments,
            normalized_arguments_digest=digest,
        )

        result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(candidate)

        assert isinstance(result, ToolAwaitingAcceptedAck)
        events = _awaiting_events(store.transaction_runner)
        request_row = next(
            event for event in events if event.event_type == "TOOL_CALL_REQUESTED"
        )
        awaiting_row = next(
            event for event in events if event.event_type == "TOOL_AWAITING"
        )
        request_payload = json.loads(request_row.payload_json)
        assert request_payload["arguments_storage_kind"] == "payload_descriptor"
        assert request_payload["arguments_inline_json"] is None
        assert isinstance(request_payload["arguments_payload_ref"], str)
        assert "x" * 100 not in request_row.payload_json
        assert "x" * 100 not in awaiting_row.payload_json
        atoms = store.transaction_runner.run_read(
            lambda transaction: tool_call_request_atoms(transaction, request_row)
        )
        assert atoms.arguments_json == {"arguments": accepted_arguments}


@pytest.mark.parametrize(
    "failure_stage",
    ("tool_awaiting_append", "run_waiting_append", "wait_record_mutation"),
)
def test_awaiting_accept_rolls_back_whole_group_after_request_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    """request append 后任一后续失败都回滚 facts/state/wait/idempotency。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _awaiting_candidate(seeded)
        event_log_store: EventLogStore
        if failure_stage == "tool_awaiting_append":
            event_log_store = _FailingEventLogStore("TOOL_AWAITING")
        elif failure_stage == "run_waiting_append":
            event_log_store = _FailingEventLogStore("RUN_WAITING")
        elif failure_stage == "wait_record_mutation":
            event_log_store = EventLogStore()
            monkeypatch.setattr(
                waiting_module,
                "insert_wait_record",
                _raise_on_wait_record_insert,
            )
        else:
            raise AssertionError("unsupported failure_stage")
        accept_port = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner,
            event_log_store=event_log_store,
        )

        with pytest.raises(RuntimeError, match="injected"):
            accept_port.accept_tool_awaiting(candidate)

        run, attempt, wait_record, events = _read_state(
            store.transaction_runner, candidate
        )
        assert run is not None
        assert run.status is RunStatus.RUNNING
        assert attempt is not None
        assert attempt.status is AttemptStatus.RUNNING
        assert wait_record is None
        assert events == ()
        scope = IdempotencyScope(
            scope_kind=IdempotencyScopeKind.TOOL_AWAITING_ACCEPT,
            scope_id=f"{candidate.attempt_id}:{candidate.tool_call_id}",
            idempotency_key=candidate.accept_idempotency_key,
        )
        idempotency_record = store.transaction_runner.run_read(
            lambda transaction: IdempotencyStore().read_idempotency_record(
                transaction, scope
            )
        )
        assert idempotency_record is None


class _SeededRun:
    """测试中创建的 active Run 引用。"""

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        attempt_id: str,
        execution_id: str,
        dispatch_record_id: str,
    ) -> None:
        """初始化 seeded run 引用。

        :param session_id: Session id。
        :param run_id: Run id。
        :param attempt_id: Attempt id。
        :param execution_id: execution id。
        :param dispatch_record_id: dispatch record id。
        :returns: ``None``。
        """

        self.session_id = session_id
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.execution_id = execution_id
        self.dispatch_record_id = dispatch_record_id


class _FailingEventLogStore(EventLogStore):
    """在指定 event type append 前注入失败的 EventLog store。"""

    def __init__(self, fail_event_type: str) -> None:
        """初始化失败注入 store。

        :param fail_event_type: 触发异常的 event type。
        :returns: ``None``。
        :raises ValueError: event type 为空时抛出。
        """

        if fail_event_type.strip() == "":
            raise ValueError("fail_event_type must be non-empty")
        self._fail_event_type = fail_event_type

    def append_event(
        self,
        transaction: HostTransaction,
        request: EventLogAppendRequest,
    ) -> EventLogAppendResult:
        """在目标 event append 前抛出测试异常。

        :param transaction: Host transaction。
        :param request: EventLog append request。
        :returns: 非目标 event 的 append result。
        :raises RuntimeError: request 命中目标 event type 时抛出。
        """

        if request.event_type == self._fail_event_type:
            raise RuntimeError(f"injected append failure: {request.event_type}")
        return super().append_event(transaction, request)


def _raise_on_wait_record_insert(
    transaction: HostTransaction,
    row: WaitRecordRow,
) -> None:
    """在 wait record mutation 处注入失败。

    :param transaction: Host transaction。
    :param row: 待写入 wait record。
    :returns: ``None``。
    :raises RuntimeError: 始终抛出以验证整段 transaction rollback。
    """

    del transaction, row
    raise RuntimeError("injected wait record mutation failure")


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _seed_active_run(transaction_runner: HostTransactionRunner) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :returns: seeded run。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="awaiting", metadata=()),
    ).snapshot.session_id
    seeded = _SeededRun(
        session_id=session_id,
        run_id="run-awaiting",
        attempt_id="attempt-awaiting",
        execution_id="execution-awaiting",
        dispatch_record_id="dispatch-awaiting",
    )

    def _operation(transaction: HostTransaction) -> None:
        """写入 active Run 所需 durable rows。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-awaiting-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        input_event = (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-input-awaiting",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=session_id,
                    run_id=seeded.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type="USER_INPUT_ACCEPTED",
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id="client-awaiting",
                    idempotency_key="idem-awaiting-input",
                    policy_decision=None,
                    reason=None,
                    payload_json={"display_text": "hello"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            .row
        )
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=seeded.run_id,
                client_request_id="client-awaiting",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-awaiting",
                run_started_event_id="event-run-started-awaiting",
                attempt_started_event_id="event-attempt-started-awaiting",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-awaiting",
                execution_target="target-awaiting",
                queue_policy=RunQueuePolicy.QUEUE,
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-awaiting-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-16T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-awaiting-test",
            lane_name="llm",
            lane_claim_id="claim-awaiting",
            lane_owner_id="owner-awaiting",
            lane_acquired_at="2026-05-16T01:02:03.000000Z",
            dispatching_at="2026-05-16T01:02:03.000000Z",
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-awaiting",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
            ),
        )

    transaction_runner.run_write(_operation)
    return seeded


def _awaiting_candidate(seeded: _SeededRun) -> ToolAwaitingAcceptCandidate:
    """构造 awaiting accept candidate。

    :param seeded: seeded run。
    :returns: awaiting accept candidate。
    """

    digest = sha256_digest_json({"awaiting": "candidate"})
    binding = WaitAdapterBinding(
        tool_name="long_tool",
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        adapter_key=WaitAdapterKey("poll:long-tool"),
        resume_policy=WaitResumePolicy.POLL,
        external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
    )
    await_spec = ToolAwaitSpec(
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        deadline=None,
        resume_token="external-job-1",
    )
    return ToolAwaitingAcceptCandidate(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        iteration_id="iteration-awaiting",
        tool_call_id="tool-call-awaiting",
        tool_name="long_tool",
        tool_schema_digest=sha256_digest_json({"schema": "long_tool"}),
        tool_identity_digest=sha256_digest_json({"identity": "long_tool"}),
        normalized_arguments_digest=sha256_digest_json({"arguments": {"name": "long_tool"}}),
        accepted_arguments={"name": "long_tool"},
        await_spec=await_spec,
        snapshot_ref=None,
        binding=binding,
        external_job_ref=binding.external_job_ref(await_spec),
        wait_id=f"wait-{digest.removeprefix('sha256:')}",
        accept_idempotency_key=f"tool-await-{digest.removeprefix('sha256:')}",
        semantic_input_digest=digest,
    )


def _read_state(
    transaction_runner: HostTransactionRunner,
    candidate: ToolAwaitingAcceptCandidate,
) -> tuple[RunRow | None, AttemptRow | None, WaitRecordRow | None, tuple[EventLogRow, ...]]:
    """读取 awaiting accept 后的 durable 状态。

    :param transaction_runner: Host transaction runner。
    :param candidate: awaiting candidate。
    :returns: Run、Attempt、wait record 与 awaiting events。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[RunRow | None, AttemptRow | None, WaitRecordRow | None, tuple[EventLogRow, ...]]:
        """读取状态。

        :param transaction: Host transaction。
        :returns: Run、Attempt、wait record 与 awaiting events。
        """

        return (
            read_run_by_id(transaction, candidate.run_id),
            read_attempt_by_id(transaction, candidate.attempt_id),
            read_wait_record_by_id(transaction, candidate.wait_id),
            tuple(
                row
                for row in EventLogStore().read_events_after(transaction, 0, limit=100)
                if row.event_type in (
                    "TOOL_CALL_REQUESTED",
                    "TOOL_AWAITING",
                    "RUN_WAITING",
                    "ATTEMPT_SUSPENDED",
                )
            ),
        )

    return transaction_runner.run_read(_operation)


def _awaiting_events(
    transaction_runner: HostTransactionRunner,
) -> tuple[EventLogRow, ...]:
    """读取 awaiting canonical events。

    :param transaction_runner: Host transaction runner。
    :returns: awaiting 事件 rows。
    """

    def _operation(transaction: HostTransaction) -> tuple[EventLogRow, ...]:
        """读取 awaiting 事件。

        :param transaction: Host transaction。
        :returns: awaiting 事件 rows。
        """

        return tuple(
            row
            for row in EventLogStore().read_events_after(transaction, 0, limit=100)
            if row.event_type in (
                "TOOL_CALL_REQUESTED",
                "TOOL_AWAITING",
                "RUN_WAITING",
                "ATTEMPT_SUSPENDED",
            )
        )

    return transaction_runner.run_read(_operation)
