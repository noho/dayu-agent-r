"""Host durable concurrency matrix 缺口测试。

本模块只补 WU-DUR-02 inspection 后仍缺少直接证据的矩阵项：
idempotency 同 key 多进程、projection checkpoint lost CAS、memory
snapshot + checkpoint CAS rollback。EventLog append、ensure_session 与
liveness 已分别由 ``test_event_log_multiprocess.py``、
``test_admission_multiprocess.py`` 和 ``test_host_instance_liveness.py``
closed by evidence；这里不重复覆盖，避免把已裁决场景扩成表面测试。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from multiprocessing import Process
from pathlib import Path

import pytest

from dayu.host.durable import projection as projection_module
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import (
    HostDurableError,
    HostIdempotencyConflictError,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.idempotency import (
    IdempotencyRecord,
    IdempotencyResultRef,
    IdempotencyScope,
    record_idempotent_result,
)
from dayu.host.durable.memory import (
    read_memory_snapshot,
    write_memory_snapshot_with_checkpoint,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.projection import (
    ProjectionCheckpointRow,
    advance_projection_checkpoint,
    read_projection_checkpoint,
)
from dayu.host.durable.schema import TABLE_IDEMPOTENCY_RECORDS
from dayu.host.durable.transaction import HostRow, HostTransaction, SQLiteScalar
from dayu.host.memory import (
    ConversationMemorySnapshotVNext,
    MemoryProjectionPolicy,
    MemorySnapshotCursor,
    build_empty_conversation_memory_snapshot,
    digest_memory_projection_policy,
    memory_snapshot_with_cursor_and_diagnostics,
)

_PROCESS_COUNT = 4
_START_GATE_TIMEOUT_SECONDS = 5.0
_START_GATE_POLL_SECONDS = 0.005
_RESULT_SEPARATOR = "|"
_RESULT_FILE_PREFIX = "worker"
_STATUS_OK = "ok"
_STATUS_CONFLICT = "conflict"
_MODE_SAME_DIGEST = "same_digest"
_MODE_DIFFERENT_DIGEST = "different_digest"
_SCOPE_KIND = "durable_matrix"
_SCOPE_ID = "session-1"
_IDEMPOTENCY_KEY = "client-request-1"
_RESULT_KIND = "event"
_CONSUMER_ID = "host.matrix.consumer"
_SESSION_ID = "session-1"
_NOW = "2026-06-01T00:00:00.000000Z"
_LATER = "2026-06-01T00:00:01.000000Z"
_STALE_SEQUENCE = 0


@dataclass(frozen=True, slots=True)
class _IdempotencySummary:
    """幂等 durable row 摘要。

    :param row_count: 当前幂等记录总行数。
    :param semantic_input_digest: durable row 中的 semantic digest。
    :param result_ref: durable row 中的 winning result ref。
    """

    row_count: int
    semantic_input_digest: str
    result_ref: str


class _RecordIdempotencyOperation:
    """写入幂等记录的 transaction operation。

    :param digest: semantic input digest。
    :param result_ref: 当前 worker 候选 result ref。
    """

    def __init__(self, digest: str, result_ref: str) -> None:
        """初始化 operation。

        :param digest: semantic input digest。
        :param result_ref: 当前 worker 候选 result ref。
        :returns: ``None``。
        """

        self._digest = digest
        self._result_ref = result_ref

    def __call__(self, transaction: HostTransaction) -> IdempotencyRecord:
        """写入或读取同 scope/key 的幂等记录。

        :param transaction: Host durable transaction。
        :returns: 新插入或已存在的幂等记录。
        :raises HostDurableError: durable 输入或写入失败时抛出。
        :raises HostIdempotencyConflictError: 同 key 已存在不同 digest 时抛出。
        """

        return record_idempotent_result(
            transaction,
            _idempotency_scope(),
            self._digest,
            IdempotencyResultRef(
                result_kind=_RESULT_KIND,
                result_ref=self._result_ref,
                created_event_id=None,
                created_event_sequence=None,
            ),
        )


class _ReadIdempotencySummaryOperation:
    """读取幂等 durable row 摘要的 transaction operation。"""

    def __call__(self, transaction: HostTransaction) -> _IdempotencySummary:
        """读取当前幂等表行数与唯一 row 内容。

        :param transaction: Host durable transaction。
        :returns: 幂等 durable row 摘要。
        :raises HostDurableError: row 结构不符合测试预期时抛出。
        """

        count_row = _require_row(
            transaction.fetchone(
                f"SELECT COUNT(*) AS row_count FROM {TABLE_IDEMPOTENCY_RECORDS}"
            ),
            "idempotency count",
        )
        row = _require_row(
            transaction.fetchone(
                f"""
                SELECT semantic_input_digest, result_ref
                FROM {TABLE_IDEMPOTENCY_RECORDS}
                WHERE scope_kind = ?
                  AND scope_id = ?
                  AND idempotency_key = ?
                """,
                (_SCOPE_KIND, _SCOPE_ID, _IDEMPOTENCY_KEY),
            ),
            "idempotency record",
        )
        return _IdempotencySummary(
            row_count=_required_int(count_row, "row_count"),
            semantic_input_digest=_required_text(row, "semantic_input_digest"),
            result_ref=_required_text(row, "result_ref"),
        )


class _AppendEventOperation:
    """追加测试 EventLog row 的 transaction operation。

    :param event_id: EventLog event id。
    :param event_type: EventLog event type。
    """

    def __init__(self, event_id: str, event_type: str) -> None:
        """初始化 operation。

        :param event_id: EventLog event id。
        :param event_type: EventLog event type。
        :returns: ``None``。
        """

        self._event_id = event_id
        self._event_type = event_type

    def __call__(self, transaction: HostTransaction) -> EventLogRow:
        """追加一条 canonical fact EventLog。

        :param transaction: Host durable transaction。
        :returns: 已追加的 EventLog row。
        :raises HostDurableError: append 失败时抛出。
        """

        return append_event(
            transaction,
            EventLogAppendRequest(
                event_id=self._event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=_SESSION_ID,
                run_id="run-1",
                attempt_id=None,
                execution_id=None,
                event_type=self._event_type,
                occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
                actor="host",
                source="durable-concurrency-matrix-test",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={"event_id": self._event_id},
                payload_ref=None,
                payload_digest=None,
            ),
        ).row


class _AdvanceCheckpointOperation:
    """推进 projection checkpoint 的 transaction operation。

    :param event: 目标 EventLog row。
    """

    def __init__(self, event: EventLogRow) -> None:
        """初始化 operation。

        :param event: 目标 EventLog row。
        :returns: ``None``。
        """

        self._event = event

    def __call__(self, transaction: HostTransaction) -> ProjectionCheckpointRow:
        """把 checkpoint 推进到目标 event。

        :param transaction: Host durable transaction。
        :returns: 推进后的 checkpoint row。
        :raises HostDurableError: checkpoint 推进失败时抛出。
        """

        return advance_projection_checkpoint(
            transaction,
            _CONSUMER_ID,
            event_sequence=self._event.event_sequence,
            event_id=self._event.event_id,
            now=_NOW,
        )


class _StaleAdvanceCheckpointOperation:
    """使用 stale checkpoint 前置条件推进 projection checkpoint。

    :param event: 目标 EventLog row。
    """

    def __init__(self, event: EventLogRow) -> None:
        """初始化 operation。

        :param event: 目标 EventLog row。
        :returns: ``None``。
        """

        self._event = event

    def __call__(self, transaction: HostTransaction) -> ProjectionCheckpointRow:
        """触发 checkpoint lost CAS race。

        :param transaction: Host durable transaction。
        :returns: 正常路径不会返回。
        :raises HostDurableError: stale checkpoint 导致 CAS 更新失败时抛出。
        """

        return advance_projection_checkpoint(
            transaction,
            _CONSUMER_ID,
            event_sequence=self._event.event_sequence,
            event_id=self._event.event_id,
            now=_LATER,
        )


class _ReadCheckpointOperation:
    """读取 projection checkpoint 的 transaction operation。"""

    def __call__(
        self, transaction: HostTransaction
    ) -> ProjectionCheckpointRow | None:
        """读取矩阵测试 consumer 的 checkpoint。

        :param transaction: Host durable transaction。
        :returns: checkpoint row 或 ``None``。
        :raises HostDurableError: durable row 类型不符合预期时抛出。
        """

        return read_projection_checkpoint(transaction, _CONSUMER_ID)


class _WriteMemorySnapshotWithCheckpointOperation:
    """写入 memory snapshot 并推进 checkpoint 的 transaction operation。

    :param snapshot: 待写入 snapshot。
    """

    def __init__(self, snapshot: ConversationMemorySnapshotVNext) -> None:
        """初始化 operation。

        :param snapshot: 待写入 snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    def __call__(self, transaction: HostTransaction) -> None:
        """写入 snapshot 并触发 checkpoint CAS。

        :param transaction: Host durable transaction。
        :returns: ``None``。
        :raises HostDurableError: checkpoint CAS 失败时抛出。
        """

        write_memory_snapshot_with_checkpoint(
            transaction,
            self._snapshot,
            now=_LATER,
        )


class _ReadMemorySnapshotExistsOperation:
    """读取指定 memory snapshot 是否存在的 transaction operation。

    :param snapshot_id: snapshot id。
    """

    def __init__(self, snapshot_id: str) -> None:
        """初始化 operation。

        :param snapshot_id: snapshot id。
        :returns: ``None``。
        """

        self._snapshot_id = snapshot_id

    def __call__(self, transaction: HostTransaction) -> bool:
        """读取 snapshot 是否已经持久化。

        :param transaction: Host durable transaction。
        :returns: snapshot 存在时返回 ``True``，否则返回 ``False``。
        :raises HostDurableError: snapshot row 损坏时抛出。
        """

        return read_memory_snapshot(transaction, self._snapshot_id) is not None


def test_idempotency_same_scope_key_same_digest_multiprocess_shares_winner(
    tmp_path: Path,
) -> None:
    """同 scope/key/same digest 多进程重放共享 winning result ref。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    _bootstrap_store(db_path, artifact_root)

    processes = _idempotency_processes(
        db_path=db_path,
        artifact_root=artifact_root,
        result_dir=result_dir,
        start_gate=start_gate,
        mode=_MODE_SAME_DIGEST,
    )
    _run_processes(processes, start_gate)

    results = tuple(
        _read_worker_fields(result_dir, worker_index)
        for worker_index in range(_PROCESS_COUNT)
    )
    statuses = tuple(fields[0] for fields in results)
    digests = tuple(fields[1] for fields in results)
    result_refs = tuple(fields[2] for fields in results)
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        summary = store.transaction_runner.run_read(
            _ReadIdempotencySummaryOperation()
        )
        assert statuses == (_STATUS_OK,) * _PROCESS_COUNT
        assert len(frozenset(digests)) == 1
        assert len(frozenset(result_refs)) == 1
        assert summary.row_count == 1
        assert summary.semantic_input_digest == digests[0]
        assert summary.result_ref == result_refs[0]


def test_idempotency_same_scope_key_different_digest_multiprocess_conflicts(
    tmp_path: Path,
) -> None:
    """同 scope/key/different digest 多进程只有一个 winner，其余冲突。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    _bootstrap_store(db_path, artifact_root)

    processes = _idempotency_processes(
        db_path=db_path,
        artifact_root=artifact_root,
        result_dir=result_dir,
        start_gate=start_gate,
        mode=_MODE_DIFFERENT_DIGEST,
    )
    _run_processes(processes, start_gate)

    results = tuple(
        _read_worker_fields(result_dir, worker_index)
        for worker_index in range(_PROCESS_COUNT)
    )
    ok_results = tuple(fields for fields in results if fields[0] == _STATUS_OK)
    conflict_results = tuple(
        fields for fields in results if fields[0] == _STATUS_CONFLICT
    )
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        summary = store.transaction_runner.run_read(
            _ReadIdempotencySummaryOperation()
        )
        assert len(ok_results) == 1
        assert len(conflict_results) == _PROCESS_COUNT - 1
        assert summary.row_count == 1
        assert summary.semantic_input_digest == ok_results[0][1]
        assert summary.result_ref == ok_results[0][2]


def test_projection_checkpoint_lost_cas_keeps_persisted_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stale checkpoint 前置条件触发 lost CAS 且旧 checkpoint 不变。"""

    options = _options(tmp_path / "durable.sqlite3", tmp_path / "artifacts")
    with open_host_durable_store(options) as store:
        first_event = store.transaction_runner.run_write(
            _AppendEventOperation("event-projection-1", "TYPE_A")
        )
        second_event = store.transaction_runner.run_write(
            _AppendEventOperation("event-projection-2", "TYPE_B")
        )
        store.transaction_runner.run_write(_AdvanceCheckpointOperation(first_event))

        monkeypatch.setattr(
            projection_module,
            "ensure_projection_checkpoint",
            _stale_projection_checkpoint,
        )
        with pytest.raises(HostDurableError) as error_info:
            store.transaction_runner.run_write(
                _StaleAdvanceCheckpointOperation(second_event)
            )
        error_message = str(error_info.value)
        checkpoint = store.transaction_runner.run_read(_ReadCheckpointOperation())

        assert "projection checkpoint advance lost CAS race" in error_message
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == first_event.event_sequence
        assert checkpoint.checkpoint_event_id == first_event.event_id


def test_memory_snapshot_checkpoint_lost_cas_rolls_back_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """memory snapshot 写入后 checkpoint CAS 失败会整体 rollback。"""

    options = _options(tmp_path / "durable.sqlite3", tmp_path / "artifacts")
    snapshot_id = "snapshot-stale-cas"
    with open_host_durable_store(options) as store:
        first_event = store.transaction_runner.run_write(
            _AppendEventOperation("event-memory-1", "TYPE_A")
        )
        second_event = store.transaction_runner.run_write(
            _AppendEventOperation("event-memory-2", "TYPE_B")
        )
        store.transaction_runner.run_write(_AdvanceCheckpointOperation(first_event))
        snapshot = _memory_snapshot_for_event(
            snapshot_id=snapshot_id,
            event_sequence=second_event.event_sequence,
            event_id=second_event.event_id,
        )

        monkeypatch.setattr(
            projection_module,
            "ensure_projection_checkpoint",
            _stale_projection_checkpoint,
        )
        with pytest.raises(HostDurableError) as error_info:
            store.transaction_runner.run_write(
                _WriteMemorySnapshotWithCheckpointOperation(snapshot)
            )
        error_message = str(error_info.value)
        snapshot_exists = store.transaction_runner.run_read(
            _ReadMemorySnapshotExistsOperation(snapshot_id)
        )
        checkpoint = store.transaction_runner.run_read(_ReadCheckpointOperation())

        assert "projection checkpoint advance lost CAS race" in error_message
        assert snapshot_exists is False
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == first_event.event_sequence
        assert checkpoint.checkpoint_event_id == first_event.event_id


def _options(db_path: Path, artifact_root: Path) -> HostDurableStoreOptions:
    """构造 Host durable store options。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=3.0,
            write_busy_retry_count=80,
            write_retry_initial_delay_seconds=0.002,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.03,
        ),
    )


def _bootstrap_store(db_path: Path, artifact_root: Path) -> None:
    """初始化 durable store schema。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(db_path, artifact_root)):
        return


def _idempotency_processes(
    *,
    db_path: Path,
    artifact_root: Path,
    result_dir: Path,
    start_gate: Path,
    mode: str,
) -> tuple[Process, ...]:
    """构造 idempotency 多进程 worker 集合。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :param result_dir: worker 结果目录。
    :param start_gate: 文件 start gate 路径。
    :param mode: 幂等 digest 模式。
    :returns: worker process 元组。
    """

    return tuple(
        Process(
            target=_idempotency_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                worker_index,
                mode,
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )


def _run_processes(processes: tuple[Process, ...], start_gate: Path) -> None:
    """启动进程、打开 start gate 并校验退出码。

    :param processes: 待运行进程。
    :param start_gate: 文件 start gate 路径。
    :returns: ``None``。
    :raises AssertionError: 任一 worker 非零退出时由断言抛出。
    """

    for process in processes:
        process.start()
    start_gate.write_text("start", encoding="utf-8")
    for process in processes:
        process.join()
        assert process.exitcode == 0


def _wait_for_start_gate(start_gate: Path) -> None:
    """等待父进程打开文件 start gate。

    :param start_gate: 文件 start gate 路径。
    :returns: ``None``。
    :raises TimeoutError: 等待超时时抛出。
    """

    deadline = time.monotonic() + _START_GATE_TIMEOUT_SECONDS
    while not start_gate.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("durable matrix start gate timeout")
        time.sleep(_START_GATE_POLL_SECONDS)


def _idempotency_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    start_gate_text: str,
    worker_index: int,
    mode: str,
) -> None:
    """子进程 worker：写入同 scope/key 的幂等结果。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: worker 结果目录文本。
    :param start_gate_text: 文件 start gate 路径文本。
    :param worker_index: worker 序号。
    :param mode: ``same_digest`` 或 ``different_digest``。
    :returns: ``None``。
    :raises HostDurableError: 非幂等冲突的 durable 错误会向子进程外抛出。
    """

    _wait_for_start_gate(Path(start_gate_text))
    digest = _worker_digest(worker_index, mode)
    result_ref = f"result-{worker_index}"
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:
        try:
            record = store.transaction_runner.run_write(
                _RecordIdempotencyOperation(digest, result_ref)
            )
        except HostIdempotencyConflictError:
            _write_worker_result(
                Path(result_dir_text),
                worker_index,
                (_STATUS_CONFLICT, digest, result_ref),
            )
        else:
            _write_worker_result(
                Path(result_dir_text),
                worker_index,
                (
                    _STATUS_OK,
                    record.semantic_input_digest,
                    record.result_ref,
                ),
            )


def _worker_digest(worker_index: int, mode: str) -> str:
    """按测试模式构造 worker semantic digest。

    :param worker_index: worker 序号。
    :param mode: ``same_digest`` 或 ``different_digest``。
    :returns: semantic input digest。
    :raises ValueError: mode 不受支持时抛出。
    """

    if mode == _MODE_SAME_DIGEST:
        return sha256_digest_json({"command": "same"})
    if mode == _MODE_DIFFERENT_DIGEST:
        return sha256_digest_json({"command": "different", "worker": worker_index})
    raise ValueError(f"unsupported idempotency worker mode: {mode}")


def _idempotency_scope() -> IdempotencyScope:
    """构造矩阵测试共用幂等 scope。

    :returns: Idempotency scope。
    """

    return IdempotencyScope(
        scope_kind=_SCOPE_KIND,
        scope_id=_SCOPE_ID,
        idempotency_key=_IDEMPOTENCY_KEY,
    )


def _write_worker_result(
    result_dir: Path, worker_index: int, fields: tuple[str, ...]
) -> None:
    """写入 worker 结果文件。

    :param result_dir: worker 结果目录。
    :param worker_index: worker 序号。
    :param fields: 需要写入的字段。
    :returns: ``None``。
    """

    result_path = result_dir / f"{_RESULT_FILE_PREFIX}-{worker_index}.txt"
    result_path.write_text(_RESULT_SEPARATOR.join(fields), encoding="utf-8")


def _read_worker_fields(result_dir: Path, worker_index: int) -> tuple[str, ...]:
    """读取 worker 结果字段。

    :param result_dir: worker 结果目录。
    :param worker_index: worker 序号。
    :returns: worker 结果字段。
    :raises AssertionError: 结果文件不存在时由断言抛出。
    """

    result_path = result_dir / f"{_RESULT_FILE_PREFIX}-{worker_index}.txt"
    assert result_path.exists()
    return tuple(result_path.read_text(encoding="utf-8").split(_RESULT_SEPARATOR))


def _stale_projection_checkpoint(
    transaction: HostTransaction, consumer_id: str, *, now: str
) -> ProjectionCheckpointRow:
    """返回确定性的 stale checkpoint，用于制造 CAS rowcount 0。

    :param transaction: Host durable transaction，本测试替身不读取它。
    :param consumer_id: projection consumer id。
    :param now: 调用方传入的当前时间，本测试替身不使用它。
    :returns: sequence 0 的 stale checkpoint row。
    """

    del transaction, now
    return ProjectionCheckpointRow(
        consumer_id=consumer_id,
        checkpoint_event_sequence=_STALE_SEQUENCE,
        checkpoint_event_id=None,
        last_success_at=None,
        updated_at=_NOW,
    )


def _memory_snapshot_for_event(
    *, snapshot_id: str, event_sequence: int, event_id: str
) -> ConversationMemorySnapshotVNext:
    """构造覆盖指定 EventLog cursor 的空 memory snapshot。

    :param snapshot_id: snapshot id。
    :param event_sequence: checkpoint event sequence。
    :param event_id: checkpoint event id。
    :returns: 重新计算 digest 后的 memory snapshot。
    :raises ValueError: cursor 字段无效时抛出。
    """

    policy = MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=8,
        selected_recent_window_char_cap=2048,
        selected_recent_window_turn_floor=2,
        fallback_selected_recent_window_item_cap=4,
        fallback_selected_recent_window_char_cap=1024,
        evidence_fact_item_cap=16,
        evidence_fact_char_cap=4096,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=4,
        answer_anchor_char_cap=1024,
        forward_intent_item_cap=4,
        forward_intent_char_cap=1024,
        reference_continuity_item_cap=4,
        reference_continuity_char_cap=1024,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
        policy_ref="durable-concurrency-test",
    )
    base = build_empty_conversation_memory_snapshot(
        snapshot_id=snapshot_id,
        session_id=_SESSION_ID,
        consumer_id=_CONSUMER_ID,
        policy_digest=digest_memory_projection_policy(policy),
        built_at=_NOW,
    )
    cursor = MemorySnapshotCursor(
        consumer_id=_CONSUMER_ID,
        checkpoint_event_sequence=event_sequence,
        checkpoint_event_id=event_id,
        session_id=_SESSION_ID,
    )
    return memory_snapshot_with_cursor_and_diagnostics(
        snapshot=base,
        cursor=cursor,
        diagnostics=(),
    )


def _require_row(row: HostRow | None, label: str) -> HostRow:
    """要求查询必须返回一行。

    :param row: 查询返回的 row。
    :param label: 诊断标签。
    :returns: 非空 HostRow。
    :raises HostDurableError: row 缺失时抛出。
    """

    if row is None:
        raise HostDurableError(f"missing {label}")
    return row


def _required_text(row: HostRow, column: str) -> str:
    """读取必填文本列。

    :param row: HostRow。
    :param column: 列名。
    :returns: 文本值。
    :raises HostDurableError: 列值不是字符串时抛出。
    """

    value = row.get(column)
    if isinstance(value, str):
        return value
    raise HostDurableError(f"{column} must be text")


def _required_int(row: HostRow, column: str) -> int:
    """读取必填整数列。

    :param row: HostRow。
    :param column: 列名。
    :returns: 整数值。
    :raises HostDurableError: 列值不是整数时抛出。
    """

    value: SQLiteScalar = row.get(column)
    if isinstance(value, int):
        return value
    raise HostDurableError(f"{column} must be int")
