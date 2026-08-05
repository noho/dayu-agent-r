"""Compaction operation transaction-local terminal owner 测试。"""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Event

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host.compaction import (
    COMPACT_OUTPUT_SCHEMA_V3,
    CompactCandidateV3,
    CompactSessionSummaryV3,
)
from dayu.host.compaction_terminal import (
    CompactionOperationTerminalDisposition,
    CompactionTerminalClosed,
    CompactionTerminalCommitPermit,
    begin_compaction_terminal_commit_in_transaction,
)
from dayu.host.context_events import CompactorProposalManifestReference
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    build_context_compacted_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from tests.host.fake_compaction import accepted_truth_for_candidate

_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_COMPETITION_TIMEOUT_SECONDS = 5.0
_BEGIN_IMMEDIATE_STATEMENT = "BEGIN IMMEDIATE"


def _successful_response_identity(
    *,
    operation_id: str,
    ordinal: int,
    compactor_engine_run_id: str,
) -> SuccessfulRunnerResponseIdentity:
    """构造 compaction terminal fixture 的 event-unique response identity。

    :param operation_id: 当前 compaction operation id。
    :param ordinal: 当前 fixture 的显式 event ordinal。
    :param compactor_engine_run_id: 当前 manifest 显式绑定的 Engine run id。
    :returns: deterministic、非敏感的成功响应身份。
    :raises ValueError: identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider="test-compactor",
        effective_model="test-compactor-model",
        runner_request_identity=build_runner_request_identity(
            run_id=compactor_engine_run_id,
            attempt_id=None,
            execution_id=None,
            iteration_id=f"{operation_id}:terminal:{ordinal}",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=ProviderRequestIdAvailability.UNAVAILABLE,
        provider_request_id=None,
    )


def _proposal_manifest_reference(
    *,
    operation_id: str,
    ordinal: int,
    compactor_engine_run_id: str,
) -> CompactorProposalManifestReference:
    """构造 compaction terminal fixture 的 typed manifest reference。

    :param operation_id: 当前 compaction operation id。
    :param ordinal: 当前 fixture 的显式 event ordinal。
    :param compactor_engine_run_id: 当前 manifest 显式绑定的 Engine run id。
    :returns: 与 operation/attempt/run 同源的 manifest reference。
    :raises ValueError: manifest binding 字段非法时抛出。
    """

    return CompactorProposalManifestReference(
        manifest_event_id=f"manifest-event:{operation_id}:{ordinal}",
        manifest_payload_ref=f"runner-call-manifest:{operation_id}:{ordinal}",
        manifest_digest=_DIGEST_A,
        compactor_input_projection_ref=f"projection:{operation_id}:{ordinal}",
        compactor_input_projection_digest=_DIGEST_B,
        compaction_operation_id=operation_id,
        compaction_attempt_number=1,
        compactor_engine_run_id=compactor_engine_run_id,
    )


class _NonCanonicalTerminalEventLogStore(EventLogStore):
    """向 owner 注入同 type non-canonical terminal row 的测试 store。"""

    def __init__(self, row: EventLogRow) -> None:
        """保存待注入 row。

        :param row: event class 已改为 non-canonical 的 terminal row。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._row = row

    def read_run_events_by_types_page(
        self,
        transaction: HostTransaction,
        *,
        run_id: str,
        event_types: tuple[str, ...],
        after_event_sequence: int,
        limit: int,
    ) -> tuple[EventLogRow, ...]:
        """返回注入 row，绕过真实 reader 的 canonical class SQL filter。

        :param transaction: 当前 Host transaction。
        :param run_id: owner 查询的 Run id。
        :param event_types: owner 查询的 terminal type 闭集。
        :param after_event_sequence: owner keyset cursor。
        :param limit: owner bounded page limit。
        :returns: 首个 page 返回注入 row，后续 page 返回空。
        :raises AssertionError: owner 查询条件漂移时抛出。
        """

        del transaction
        assert run_id == self._row.run_id
        assert self._row.event_type in event_types
        assert limit > 0
        if after_event_sequence >= self._row.event_sequence:
            return ()
        return (self._row,)


@dataclass(frozen=True, slots=True)
class _CompetingTerminalWriter:
    """在独立真实 connection 上竞争同一 operation terminal 的 writer。

    :param options: 两个 writer 共用的 durable store options。
    :param operation_id: 两个 writer 竞争的 operation id。
    :param terminal_type: 本 writer 获得 permit 时计划提交的 terminal type。
    :param ordinal: 本 writer terminal fixture ordinal。
    :param ready: connection 与 runner 已准备完成的 barrier。
    :param start: 允许本 writer 调用 ``run_write`` 的 barrier。
    :param permit_acquired: 本 writer 获得 permit 后发布的可选 barrier。
    :param release_permit: 本 writer 获得 permit 后等待的可选 barrier。
    :param begin_attempted: trace 观察到 ``BEGIN IMMEDIATE`` 的可选 barrier。
    """

    options: HostDurableStoreOptions
    operation_id: str
    terminal_type: str
    ordinal: int
    ready: Event
    start: Event
    permit_acquired: Event | None
    release_permit: Event | None
    begin_attempted: Event | None

    def __call__(
        self,
    ) -> CompactionTerminalCommitPermit | CompactionTerminalClosed:
        """打开 thread-owned connection 并执行一次 terminal competition。

        :returns: production owner 返回的 permit 或 closed disposition。
        :raises TimeoutError: start/release barrier 未在有界时间内触发时抛出。
        :raises Exception: durable connection、transaction 或 append 失败时透传。
        """

        store = open_host_durable_store(self.options)
        connection = store.connect()
        try:
            connection.set_trace_callback(self._record_statement)
            runner = HostTransactionRunner(
                connection,
                self.options.sqlite_policy,
                artifact_root=self.options.payload_policy.artifact_root,
                payload_inline_threshold_bytes=(self.options.payload_policy.payload_inline_threshold_bytes),
                create_artifact_root=(self.options.payload_policy.create_artifact_root),
            )
            self.ready.set()
            if not self.start.wait(_COMPETITION_TIMEOUT_SECONDS):
                raise TimeoutError("compaction writer start barrier timed out")
            return runner.run_write(self._commit_terminal)
        finally:
            connection.close()
            store.close()

    def _record_statement(self, statement: str) -> None:
        """记录本 writer 已实际尝试执行 ``BEGIN IMMEDIATE``。

        :param statement: SQLite trace callback 产生的 SQL statement。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self.begin_attempted is not None and statement.strip().upper() == _BEGIN_IMMEDIATE_STATEMENT:
            self.begin_attempted.set()

    def _commit_terminal(
        self,
        transaction: HostTransaction,
    ) -> CompactionTerminalCommitPermit | CompactionTerminalClosed:
        """在 transaction 内取得 permit，并仅由 winner 追加 terminal。

        :param transaction: production runner 提供的真实 write transaction。
        :returns: production owner 返回的 permit 或 closed disposition。
        :raises TimeoutError: winner release barrier 未在有界时间内触发时抛出。
        :raises Exception: owner 判定或 terminal append 失败时透传。
        """

        result = begin_compaction_terminal_commit_in_transaction(
            transaction,
            EventLogStore(),
            operation_id=self.operation_id,
            expected_trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        )
        if not isinstance(result, CompactionTerminalCommitPermit):
            return result
        if self.permit_acquired is not None:
            self.permit_acquired.set()
        if self.release_permit is not None and not self.release_permit.wait(_COMPETITION_TIMEOUT_SECONDS):
            raise TimeoutError("compaction writer permit release timed out")
        _append_terminal(
            transaction,
            operation_id=self.operation_id,
            terminal_type=self.terminal_type,
            ordinal=self.ordinal,
        )
        return result


@pytest.mark.parametrize(
    "trigger_source",
    (
        ContextCompactionTriggerSource.PROACTIVE,
        ContextCompactionTriggerSource.REACTIVE,
    ),
)
def test_open_operation_returns_trigger_aware_transaction_local_permit(
    tmp_path: Path,
    trigger_source: ContextCompactionTriggerSource,
) -> None:
    """两类合法 request 都由 shared owner 返回精确 OPEN permit。

    :param tmp_path: pytest 临时目录。
    :param trigger_source: 本例 request/writer trigger。
    :returns: ``None``。
    :raises AssertionError: owner 未返回同源 OPEN permit 时抛出。
    """

    with open_host_durable_store(_durable_options(tmp_path)) as store:
        operation_id = f"operation-{trigger_source.value}"

        def _operation(transaction: HostTransaction) -> CompactionTerminalCommitPermit:
            """追加 request 并在同一事务读取 permit。

            :param transaction: 当前 Host write transaction。
            :returns: 已验证 OPEN permit。
            :raises AssertionError: owner 返回 closed 时抛出。
            """

            request = _append_request(
                transaction,
                operation_id=operation_id,
                trigger_source=trigger_source,
            )
            result = begin_compaction_terminal_commit_in_transaction(
                transaction,
                EventLogStore(),
                operation_id=operation_id,
                expected_trigger_source=trigger_source,
            )
            assert isinstance(result, CompactionTerminalCommitPermit)
            assert result.request_event_sequence == request.event_sequence
            return result

        permit = store.transaction_runner.run_write(_operation)
        assert permit.operation_id == operation_id
        assert permit.trigger_source is trigger_source


def test_two_competing_terminal_writers_commit_exactly_one_canonical_terminal(
    tmp_path: Path,
) -> None:
    """同一 operation 的两个真实 writer 必须只有一个取得 permit 并提交。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: competition 未真实发生或出现第二 terminal 时抛出。
    :raises Exception: durable setup、transaction 或 worker 失败时透传。
    """

    options = _durable_options(tmp_path)
    operation_id = "operation-two-competing-writers"
    with open_host_durable_store(options) as store:
        store.transaction_runner.run_write(
            partial(
                _append_request,
                operation_id=operation_id,
                trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
        )

    winner_ready = Event()
    loser_ready = Event()
    winner_start = Event()
    loser_start = Event()
    winner_has_permit = Event()
    release_winner = Event()
    loser_begin_attempted = Event()
    winner = _CompetingTerminalWriter(
        options=options,
        operation_id=operation_id,
        terminal_type=CONTEXT_COMPACTED,
        ordinal=1,
        ready=winner_ready,
        start=winner_start,
        permit_acquired=winner_has_permit,
        release_permit=release_winner,
        begin_attempted=None,
    )
    loser = _CompetingTerminalWriter(
        options=options,
        operation_id=operation_id,
        terminal_type=CONTEXT_COMPACTION_FAILED,
        ordinal=2,
        ready=loser_ready,
        start=loser_start,
        permit_acquired=None,
        release_permit=None,
        begin_attempted=loser_begin_attempted,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        winner_future = executor.submit(winner)
        loser_future = executor.submit(loser)
        assert winner_ready.wait(_COMPETITION_TIMEOUT_SECONDS)
        assert loser_ready.wait(_COMPETITION_TIMEOUT_SECONDS)
        winner_start.set()
        assert winner_has_permit.wait(_COMPETITION_TIMEOUT_SECONDS)
        loser_start.set()
        try:
            assert loser_begin_attempted.wait(_COMPETITION_TIMEOUT_SECONDS)
            assert not loser_future.done()
        finally:
            release_winner.set()
        winner_result = winner_future.result(_COMPETITION_TIMEOUT_SECONDS)
        loser_result = loser_future.result(_COMPETITION_TIMEOUT_SECONDS)

    assert isinstance(winner_result, CompactionTerminalCommitPermit)
    assert isinstance(loser_result, CompactionTerminalClosed)
    assert loser_result.disposition is CompactionOperationTerminalDisposition.COMPACTED
    assert loser_result.first_terminal_event_type == CONTEXT_COMPACTED

    store = open_host_durable_store(options)
    try:
        closed, terminal_rows = store.transaction_runner.run_write(
            partial(
                _read_terminal_competition_state,
                operation_id=operation_id,
            )
        )
    finally:
        store.close()
    assert closed.disposition is CompactionOperationTerminalDisposition.COMPACTED
    assert closed.first_terminal_event_type == CONTEXT_COMPACTED
    assert len(terminal_rows) == 1
    assert terminal_rows[0].event_type == CONTEXT_COMPACTED


def test_trigger_mismatch_fails_closed(tmp_path: Path) -> None:
    """reactive writer 不得取得 proactive request 的 terminal permit。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: trigger mismatch 未 fail closed 时抛出。
    """

    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> None:
            """构造 mismatch 并断言 owner fail closed。

            :param transaction: 当前 Host write transaction。
            :returns: ``None``。
            :raises AssertionError: trigger mismatch 未 fail closed 时抛出。
            """

            _append_request(
                transaction,
                operation_id="operation-trigger-mismatch",
                trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            with pytest.raises(HostDurableError, match="trigger source"):
                begin_compaction_terminal_commit_in_transaction(
                    transaction,
                    EventLogStore(),
                    operation_id="operation-trigger-mismatch",
                    expected_trigger_source=(ContextCompactionTriggerSource.REACTIVE),
                )

        store.transaction_runner.run_write(_operation)


@pytest.mark.parametrize(
    ("terminal_type", "expected_disposition"),
    (
        (
            CONTEXT_COMPACTED,
            CompactionOperationTerminalDisposition.COMPACTED,
        ),
        (
            CONTEXT_COMPACTION_FAILED,
            CompactionOperationTerminalDisposition.FAILED,
        ),
    ),
)
def test_first_terminal_projects_exact_sequence_and_type(
    tmp_path: Path,
    terminal_type: str,
    expected_disposition: CompactionOperationTerminalDisposition,
) -> None:
    """first compacted/failed 由 shared owner 投影 exact closed truth。

    :param tmp_path: pytest 临时目录。
    :param terminal_type: 本例写入的 terminal event type。
    :param expected_disposition: 预期封闭 disposition。
    :returns: ``None``。
    :raises AssertionError: first terminal sequence/type/disposition 漂移时抛出。
    """

    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> tuple[EventLogRow, CompactionTerminalClosed]:
            """追加 request/terminal 并读取 closed result。

            :param transaction: 当前 Host write transaction。
            :returns: terminal row 与 closed result。
            :raises AssertionError: owner 未返回 closed 时抛出。
            """

            operation_id = f"operation-first-{terminal_type.lower()}"
            _append_request(
                transaction,
                operation_id=operation_id,
                trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            terminal = _append_terminal(
                transaction,
                operation_id=operation_id,
                terminal_type=terminal_type,
                ordinal=1,
            )
            result = begin_compaction_terminal_commit_in_transaction(
                transaction,
                EventLogStore(),
                operation_id=operation_id,
                expected_trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            assert isinstance(result, CompactionTerminalClosed)
            return terminal, result

        terminal, closed = store.transaction_runner.run_write(_operation)
        assert closed.disposition is expected_disposition
        assert closed.first_terminal_event_sequence == terminal.event_sequence
        assert closed.first_terminal_event_type == terminal_type


def test_multiple_terminals_fail_closed_without_inventing_third_truth(
    tmp_path: Path,
) -> None:
    """已有两个 terminal 时返回 INVALID_MULTIPLE 并保留 first truth。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: multiple terminals 未投影为 INVALID_MULTIPLE 时抛出。
    """

    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> CompactionTerminalClosed:
            """构造损坏 terminal history 并读取 owner disposition。

            :param transaction: 当前 Host write transaction。
            :returns: INVALID_MULTIPLE closed result。
            :raises AssertionError: owner 未返回 closed 时抛出。
            """

            operation_id = "operation-multiple"
            _append_request(
                transaction,
                operation_id=operation_id,
                trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            first = _append_terminal(
                transaction,
                operation_id=operation_id,
                terminal_type=CONTEXT_COMPACTION_FAILED,
                ordinal=1,
            )
            _append_terminal(
                transaction,
                operation_id=operation_id,
                terminal_type=CONTEXT_COMPACTED,
                ordinal=2,
            )
            result = begin_compaction_terminal_commit_in_transaction(
                transaction,
                EventLogStore(),
                operation_id=operation_id,
                expected_trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            assert isinstance(result, CompactionTerminalClosed)
            assert result.first_terminal_event_sequence == first.event_sequence
            return result

        closed = store.transaction_runner.run_write(_operation)
        assert closed.disposition is CompactionOperationTerminalDisposition.INVALID_MULTIPLE
        assert closed.first_terminal_event_type == CONTEXT_COMPACTION_FAILED


def test_arbitrary_event_cannot_act_as_compaction_request(tmp_path: Path) -> None:
    """shared owner 拒绝任意非 compaction request event。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任意 event 获得 terminal permit 时抛出。
    """

    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> None:
            """追加任意 canonical event 并断言 owner fail closed。

            :param transaction: 当前 Host write transaction。
            :returns: ``None``。
            :raises AssertionError: 任意 event 获得 terminal permit 时抛出。
            """

            EventLogStore().append_event(
                transaction,
                _event_request(
                    event_id="operation-arbitrary",
                    event_type="RUN_ACCEPTED",
                    payload_json={"operation_id": "operation-arbitrary"},
                ),
            )
            with pytest.raises(HostDurableError, match="request identity"):
                begin_compaction_terminal_commit_in_transaction(
                    transaction,
                    EventLogStore(),
                    operation_id="operation-arbitrary",
                    expected_trigger_source=(ContextCompactionTriggerSource.PROACTIVE),
                )

        store.transaction_runner.run_write(_operation)


def test_non_canonical_terminal_row_fails_before_operation_filter(
    tmp_path: Path,
) -> None:
    """同 type non-canonical row 不能成为 winner 或绕过 event-class invariant。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: non-canonical row 绕过 event-class invariant 时抛出。
    """

    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> None:
            """注入 non-canonical terminal 并断言 shared owner fail closed。

            :param transaction: 当前 Host write transaction。
            :returns: ``None``。
            :raises AssertionError: non-canonical row 未 fail closed 时抛出。
            """

            operation_id = "operation-non-canonical-terminal"
            _append_request(
                transaction,
                operation_id=operation_id,
                trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            canonical = _append_terminal(
                transaction,
                operation_id="different-operation",
                terminal_type=CONTEXT_COMPACTION_FAILED,
                ordinal=9,
            )
            injected = replace(
                canonical,
                event_class=EventClass.DIAGNOSTIC,
            )
            with pytest.raises(HostDurableError, match="event class"):
                begin_compaction_terminal_commit_in_transaction(
                    transaction,
                    _NonCanonicalTerminalEventLogStore(injected),
                    operation_id=operation_id,
                    expected_trigger_source=(ContextCompactionTriggerSource.PROACTIVE),
                )

        store.transaction_runner.run_write(_operation)


def test_compaction_terminal_writer_inventory_uses_only_shared_owner() -> None:
    """两路 request-backed terminal outcome writer 只使用 shared owner。

    既有 hard-threshold/material-source/reactive-precondition failure 没有
    ``CONTEXT_COMPACTION_REQUESTED``，因此明确属于 operation 外诊断；本测试
    同时固定它们不能被误当作第二套 request-backed guard。

    :returns: ``None``。
    :raises AssertionError: operation outcome 缺 guard、guard 数量漂移或出现第二
        terminal count owner 时抛出。
    """

    repository_root = Path(__file__).resolve().parents[2]
    dispatch_source = (repository_root / "dayu/host/dispatch.py").read_text(encoding="utf-8")
    engine_source = (repository_root / "dayu/host/engine_ingest.py").read_text(encoding="utf-8")
    proactive_source = (repository_root / "dayu/host/proactive_compaction.py").read_text(encoding="utf-8")
    dispatch_module = ast.parse(dispatch_source)
    engine_module = ast.parse(engine_source)
    proactive_module = ast.parse(proactive_source)

    assert (
        len(
            _call_lines(
                dispatch_module,
                "begin_compaction_terminal_commit_in_transaction",
            )
        )
        == 4
    )
    assert (
        len(
            _call_lines(
                engine_module,
                "begin_compaction_terminal_commit_in_transaction",
            )
        )
        == 1
    )
    assert (
        len(
            _call_lines(
                proactive_module,
                "begin_compaction_terminal_commit_in_transaction",
            )
        )
        == 1
    )
    assert "terminal_count" not in proactive_source
    assert "terminal_count" not in dispatch_source
    assert "terminal_count" not in engine_source

    proactive_execute = _function_node(
        dispatch_module,
        "_execute_proactive_compaction",
    )
    execute_guards = _call_lines(
        proactive_execute,
        "begin_compaction_terminal_commit_in_transaction",
    )
    execute_writers = tuple(
        sorted(
            (
                *_call_lines(proactive_execute, "_append_compacted_event"),
                *_call_lines(
                    proactive_execute,
                    "_append_compaction_failed_event",
                ),
                *_call_lines(
                    proactive_execute,
                    "_append_compaction_failed_with_proactive_fallback",
                ),
            )
        )
    )
    assert len(execute_guards) == 1
    assert len(execute_writers) == 4
    assert all(line > execute_guards[0] for line in execute_writers)

    proactive_prepare = _function_node(
        dispatch_module,
        "_prepare_compact_before_dispatch",
    )
    prepare_guards = _call_lines(
        proactive_prepare,
        "begin_compaction_terminal_commit_in_transaction",
    )
    prepare_writers = _call_lines(
        proactive_prepare,
        "_append_compaction_failed_with_proactive_fallback",
    )
    assert len(prepare_guards) == 2
    assert len(prepare_writers) == 2
    assert all(
        guard_line < writer_line
        for guard_line, writer_line in zip(
            prepare_guards,
            prepare_writers,
            strict=True,
        )
    )

    proactive_governance = _function_node(
        dispatch_module,
        "_run_pre_start_governance",
    )
    governance_guards = _call_lines(
        proactive_governance,
        "begin_compaction_terminal_commit_in_transaction",
    )
    governance_operation_writers = _call_lines(
        proactive_governance,
        "_append_compaction_failed_with_proactive_fallback",
    )
    governance_precondition_writers = _call_lines(
        proactive_governance,
        "_append_compaction_failed_event",
    )
    assert len(governance_guards) == 1
    assert len(governance_operation_writers) == 1
    assert governance_operation_writers[0] > governance_guards[0]
    assert len(governance_precondition_writers) == 2
    assert all(line < governance_guards[0] for line in governance_precondition_writers)
    assert dispatch_source.count("_precondition_compaction_operation_id(") == 3

    reactive_execute = _function_node(
        engine_module,
        "_execute_reactive_compaction",
    )
    reactive_guards = _call_lines(
        reactive_execute,
        "begin_compaction_terminal_commit_in_transaction",
    )
    reactive_writers = tuple(
        sorted(
            (
                *_call_lines(
                    reactive_execute,
                    "_append_reactive_compacted_event",
                ),
                *_call_lines(
                    reactive_execute,
                    "_append_reactive_compaction_failed_event",
                ),
            )
        )
    )
    assert len(reactive_guards) == 1
    assert len(reactive_writers) == 3
    assert all(line > reactive_guards[0] for line in reactive_writers)
    assert engine_source.count("_reactive_precondition_compaction_operation_id(") == 2


def _function_node(
    module: ast.Module,
    function_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """按名称读取唯一函数 AST node。

    :param module: 已解析 Python module。
    :param function_name: 目标函数名。
    :returns: 唯一匹配的同步或异步函数 node。
    :raises AssertionError: 找不到唯一函数时抛出。
    """

    matches = tuple(
        node
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    assert len(matches) == 1
    return matches[0]


def _call_lines(node: ast.AST, callable_name: str) -> tuple[int, ...]:
    """读取 AST node 内指定 callable 的全部调用行号。

    :param node: 待扫描 AST node。
    :param callable_name: 目标直接函数名或 attribute 名。
    :returns: 按升序排列的调用行号。
    :raises Exception: 不主动抛出异常。
    """

    lines: list[int] = []
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call):
            continue
        function = candidate.func
        if (isinstance(function, ast.Name) and function.id == callable_name) or (
            isinstance(function, ast.Attribute) and function.attr == callable_name
        ):
            lines.append(candidate.lineno)
    return tuple(sorted(lines))


def _append_request(
    transaction: HostTransaction,
    *,
    operation_id: str,
    trigger_source: ContextCompactionTriggerSource,
) -> EventLogRow:
    """追加测试用合法 compaction request。

    :param transaction: 当前 Host write transaction。
    :param operation_id: request/operation id。
    :param trigger_source: proactive 或 reactive trigger。
    :returns: 已提交 request row。
    :raises Exception: request payload 或 EventLog append 失败时透传。
    """

    reactive = trigger_source is ContextCompactionTriggerSource.REACTIVE
    return (
        EventLogStore()
        .append_event(
            transaction,
            _event_request(
                event_id=operation_id,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                payload_json=build_context_compaction_requested_payload(
                    operation_id=operation_id,
                    max_compaction_attempts_per_operation=5,
                    trigger_source=trigger_source,
                    budget_reason="test",
                    budget_snapshot_ref="budget:test",
                    input_snapshot_cursor=1,
                    estimator_digest=_DIGEST_A,
                    policy_ref="policy:test",
                    provider_request_id=None,
                    provider_error_ref=None,
                    attempt_id="attempt-test" if reactive else None,
                    execution_id="execution-test" if reactive else None,
                    client_correlation_id=None,
                    frozen_material_list_digest=_DIGEST_B,
                    frozen_material_refs=("event-input-test",),
                ),
            ),
        )
        .row
    )


def _append_terminal(
    transaction: HostTransaction,
    *,
    operation_id: str,
    terminal_type: str,
    ordinal: int,
) -> EventLogRow:
    """追加测试用 compacted 或 failed terminal。

    :param transaction: 当前 Host write transaction。
    :param operation_id: request/operation id。
    :param terminal_type: compacted 或 failed event type。
    :param ordinal: terminal event id 区分序号。
    :returns: 已提交 terminal row。
    :raises AssertionError: terminal type 不在闭集时抛出。
    :raises Exception: payload 或 EventLog append 失败时透传。
    """

    if terminal_type == CONTEXT_COMPACTED:
        payload = build_context_compacted_payload(
            operation_id=operation_id,
            accepted_attempt_number=1,
            compact_artifact_ref=f"artifact:{ordinal}",
            compact_artifact_digest=_DIGEST_A,
            accepted_truth=accepted_truth_for_candidate(
                _candidate(),
                current_input_ref="event-current-protected",
                source_refs_by_label={"T1": ("event-input-test",)},
            ),
            budget_after_compact=1,
            prompt_local_label_mapping_refs=("label:test",),
            accepted_evidence_mapping_refs=(),
            projection_signal="conversation_memory_projection_catchup",
            successful_response_identity=_successful_response_identity(
                operation_id=operation_id,
                ordinal=ordinal,
                compactor_engine_run_id=f"compactor-run:{operation_id}:{ordinal}",
            ),
            accepted_proposal_manifest_reference=_proposal_manifest_reference(
                operation_id=operation_id,
                ordinal=ordinal,
                compactor_engine_run_id=f"compactor-run:{operation_id}:{ordinal}",
            ),
        )
    else:
        assert terminal_type == CONTEXT_COMPACTION_FAILED
        payload = build_context_compaction_failed_payload(
            operation_id=operation_id,
            failure_reason="test_failure",
            policy_decision="fail_closed",
            retryable=False,
            attempt_count=0,
            retry_repair_budget_exhausted=False,
            diagnostic_refs=("diagnostic:test",),
            budget_after_attempted_compact=None,
        )
    return (
        EventLogStore()
        .append_event(
            transaction,
            _event_request(
                event_id=f"terminal-{ordinal}-{terminal_type.lower()}",
                event_type=terminal_type,
                payload_json=payload,
            ),
        )
        .row
    )


def _read_terminal_competition_state(
    transaction: HostTransaction,
    *,
    operation_id: str,
) -> tuple[CompactionTerminalClosed, tuple[EventLogRow, ...]]:
    """读取竞争结束后的 owner disposition 与全部 terminal rows。

    :param transaction: 用于 fresh owner read 的真实 write transaction。
    :param operation_id: 已完成竞争的 compaction operation id。
    :returns: closed owner disposition 与测试 Run 的全部 canonical terminal rows。
    :raises AssertionError: operation 竞争后仍开放时抛出。
    :raises Exception: durable owner 或 EventLog read 失败时透传。
    """

    result = begin_compaction_terminal_commit_in_transaction(
        transaction,
        EventLogStore(),
        operation_id=operation_id,
        expected_trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    )
    if not isinstance(result, CompactionTerminalClosed):
        raise AssertionError("compaction competition operation must be closed")
    terminal_rows = EventLogStore().read_run_events_by_types_page(
        transaction,
        run_id="run-test",
        event_types=(CONTEXT_COMPACTED, CONTEXT_COMPACTION_FAILED),
        after_event_sequence=0,
        limit=64,
    )
    return result, terminal_rows


def _event_request(
    *,
    event_id: str,
    event_type: str,
    payload_json: Mapping[str, JsonValue],
) -> EventLogAppendRequest:
    """构造测试用 canonical event append request。

    :param event_id: event id。
    :param event_type: canonical event type。
    :param payload_json: JSON payload。
    :returns: append request。
    :raises TypeError: payload 不是 JSON value 时由 EventLog owner 抛出。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-test",
        run_id="run-test",
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=datetime.now(UTC),
        actor="pytest",
        source="tests.host.test_compaction_terminal",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json=payload_json,
        payload_ref=None,
        payload_digest=None,
    )


def _candidate() -> CompactCandidateV3:
    """构造最小非空合法 compact candidate。

    :returns: 合法 vNext compact candidate。
    :raises Exception: candidate contract 构造失败时透传。
    """

    return CompactCandidateV3(
        schema=COMPACT_OUTPUT_SCHEMA_V3,
        session_summary=CompactSessionSummaryV3(
            text="保留 terminal 测试状态",
            source_labels=("T1",),
        ),
        evidence_facts=(),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
    )


def _durable_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试 durable store 选项。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    :raises Exception: options contract 构造失败时透传。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts",
        ),
    )
