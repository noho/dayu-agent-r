"""Host P6 ProjectionStore + ProjectionCoordinator 行为测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

import pytest

from dayu.contracts import JsonValue
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine import (
    ContentDeltaData,
    FinalAnswerData,
    FinishReason,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)
from dayu.host._audit_projection import AuditProjectionObserver
from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._event_observer import (
    NonTransactionalObserverSink,
    ObserverDescriptor,
    ProjectionCoordinator,
    ProjectionEventEnvelope,
    RetryableProjectionError,
)
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import GlobalEventPosition, ObserverStatus
from dayu.host._projection_store import ProjectionStore
from dayu.host._tool_trace_jsonl_sink import ToolTraceJsonlSink
from dayu.host._tool_trace_projection import ToolTraceObserver
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
)
from utils.analyze_tool_trace_host import analyze_trace_root


def _utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _content_draft(*, run_id: str, idx: int) -> RunEventDraft:
    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUNNER_CONTENT_DELTA,
        occurred_at=_utc(),
        data=ContentDeltaData(iteration_id="iter", delta=f"d{idx}"),
        source_engine_event_id=f"engine_{run_id}_{idx}",
    )


def _final_draft(run_id: str) -> RunEventDraft:
    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=_utc(),
        data=FinalAnswerData(
            content="ok",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        source_engine_event_id=f"engine_final_{run_id}",
    )


def _tool_call_requested_draft(*, run_id: str, tool_call_id: str) -> RunEventDraft:
    """构造工具调用请求事件草稿。

    :param run_id: Run id。
    :param tool_call_id: 工具调用 id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.TOOL_CALL_REQUESTED,
        occurred_at=_utc(),
        data=ToolCallRequestedData(
            iteration_id="iter",
            tool_call_id=tool_call_id,
            name="echo",
            arguments={"text": "hi"},
            index_in_iteration=0,
            provider_state=None,
        ),
        source_engine_event_id=None,
    )


def _tool_call_accepted_draft(*, run_id: str, tool_call_id: str) -> RunEventDraft:
    """构造工具调用结果接受事件草稿。

    :param run_id: Run id。
    :param tool_call_id: 工具调用 id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.TOOL_RESULT_ACCEPTED,
        occurred_at=_utc(),
        data=ToolResultAcceptedData(
            iteration_id="iter",
            tool_call_id=tool_call_id,
            name="echo",
            index_in_iteration=0,
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=cast(Literal[True], True),
                    value={"answer": "ok"},
                    truncation=None,
                    meta=None,
                )
            ),
        ),
        source_engine_event_id=None,
    )


def _read_trace_jsonl_lines(*, root: Path, session_id: str) -> list[dict[str, JsonValue]]:
    """读取指定 session 下的 tool trace JSONL 行。

    :param root: trace 根目录。
    :param session_id: session id。
    :returns: 解析后的 JSON record 列表。
    :raises json.JSONDecodeError: JSONL 行不是合法 JSON 时抛出。
    """

    session_dir = root / "sessions" / session_id
    if not session_dir.exists():
        return []
    records: list[dict[str, JsonValue]] = []
    for path in sorted(session_dir.glob("tool_calls_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                records.append(cast(dict[str, JsonValue], json.loads(line)))
    return records


@pytest.mark.asyncio
async def test_projection_checkpoint_advances_after_drain() -> None:
    """observer drain 完成后 checkpoint 应该推进到 latest position。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))
    await store.append(_final_draft("r1"))

    observer = AuditProjectionObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(observer,),
    )
    snapshots = await coord.drain()
    assert len(snapshots) == 1
    cp = snapshots[0]
    assert cp.last_success_position is not None
    assert cp.last_success_position.value == 2
    assert cp.status in {ObserverStatus.RUNNING, ObserverStatus.CAUGHT_UP}
    assert len(observer.list_records()) == 2
    storage.close()


class _RetryOnceObserver:
    """测试用 observer，第一次抛 retryable，第二次成功。"""

    def __init__(self) -> None:
        self._calls = 0
        self.processed_positions: list[int] = []

    @property
    def descriptor(self) -> ObserverDescriptor:
        return ObserverDescriptor(
            observer_id="retry_once",
            projection_name="retry_test",
            schema_version=1,
            required=False,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        del tx
        self._calls += 1
        if self._calls == 1:
            raise RetryableProjectionError("transient")
        for env in batch:
            self.processed_positions.append(env.position.value)


@pytest.mark.asyncio
async def test_observer_retryable_failure_does_not_advance() -> None:
    """RetryableProjectionError 必须只标 RETRYABLE_FAILED，不前进。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))

    observer = _RetryOnceObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(observer,),
    )
    await coord.initialize()
    snap1 = await coord.run_once(observer=observer)
    assert snap1.status is ObserverStatus.RETRYABLE_FAILED
    assert snap1.last_success_position is None
    assert snap1.retry_count >= 1

    snap2 = await coord.run_once(observer=observer)
    assert snap2.status in {ObserverStatus.RUNNING, ObserverStatus.CAUGHT_UP}
    assert snap2.last_success_position is not None
    assert observer.processed_positions == [1]
    storage.close()


class _BlockingObserver:
    """非 retryable 异常 observer，验证 BLOCKED_FAILED 路径。"""

    @property
    def descriptor(self) -> ObserverDescriptor:
        return ObserverDescriptor(
            observer_id="blocking",
            projection_name="blocking_test",
            schema_version=1,
            required=True,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        del tx, batch
        raise RuntimeError("blocked")


class _RequiredRecordingObserver:
    """required observer，记录处理过的 event position。"""

    def __init__(self) -> None:
        """初始化记录容器。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.processed_positions: list[int] = []

    @property
    def descriptor(self) -> ObserverDescriptor:
        """返回 required observer 描述符。

        :returns: ObserverDescriptor。
        :raises Exception: 不主动抛出异常。
        """

        return ObserverDescriptor(
            observer_id="required_memory_like",
            projection_name="required_projection",
            schema_version=1,
            required=True,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """记录 batch position。

        :param tx: 当前事务。
        :param batch: 事件 envelope。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        del tx
        for envelope in batch:
            self.processed_positions.append(envelope.position.value)


class _FailingNonTransactionalObserver:
    """非 required 非事务 observer，模拟 JSONL/blob I/O 失败。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.call_count = 0

    @property
    def descriptor(self) -> ObserverDescriptor:
        """返回非 required observer 描述符。

        :returns: ObserverDescriptor。
        :raises Exception: 不主动抛出异常。
        """

        return ObserverDescriptor(
            observer_id="non_required_trace_like",
            projection_name="trace_projection",
            schema_version=1,
            required=False,
        )

    async def process_non_transactional(
        self,
        *,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """模拟 transaction 外 sink I/O 失败。

        :param batch: 事件 envelope。
        :returns: 无返回值。
        :raises OSError: 始终抛出，用于验证 checkpoint 不推进。
        """

        del batch
        self.call_count += 1
        raise OSError("disk full")


class _RecordingNonTransactionalObserver:
    """非 required 非事务 observer，记录每次 sink 写入的 batch。"""

    def __init__(self) -> None:
        """初始化记录容器。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.written_batches: list[tuple[int, ...]] = []

    @property
    def descriptor(self) -> ObserverDescriptor:
        """返回非 required observer 描述符。

        :returns: ObserverDescriptor。
        :raises Exception: 不主动抛出异常。
        """

        return ObserverDescriptor(
            observer_id="non_required_trace_success",
            projection_name="trace_projection",
            schema_version=1,
            required=False,
        )

    async def process_non_transactional(
        self,
        *,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """记录 transaction 外 sink 写入。

        :param batch: 事件 envelope。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.written_batches.append(tuple(envelope.position.value for envelope in batch))


class _CheckpointFailOnceProjectionStore(ProjectionStore):
    """指定 observer 第一次 advance_success 时模拟 checkpoint 失败。"""

    def __init__(self, *, storage: HostStorage, observer_id: str) -> None:
        """初始化 projection store。

        :param storage: 共享 HostStorage。
        :param observer_id: 需要触发一次失败的 observer id。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(storage=storage)
        self._observer_id = observer_id
        self._failed_once = False

    def advance_success(
        self,
        *,
        tx: HostStorageTransaction,
        observer_id: str,
        projection_name: str,
        schema_version: int,
        position: GlobalEventPosition,
        status: ObserverStatus,
    ) -> None:
        """第一次推进指定 observer checkpoint 时抛错。

        :param tx: 当前事务。
        :param observer_id: observer id。
        :param projection_name: projection 名。
        :param schema_version: schema 版本。
        :param position: 成功位置。
        :param status: checkpoint 状态。
        :returns: 无返回值。
        :raises RuntimeError: 指定 observer 第一次推进时抛出。
        """

        if observer_id == self._observer_id and not self._failed_once:
            self._failed_once = True
            raise RuntimeError("checkpoint write failed")
        super().advance_success(
            tx=tx,
            observer_id=observer_id,
            projection_name=projection_name,
            schema_version=schema_version,
            position=position,
            status=status,
        )


@pytest.mark.asyncio
async def test_observer_non_retryable_failure_marks_blocked() -> None:
    """普通异常进入 BLOCKED_FAILED，不前进 success position。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))

    observer = _BlockingObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(observer,),
    )
    await coord.initialize()
    snap = await coord.run_once(observer=observer)
    assert snap.status is ObserverStatus.BLOCKED_FAILED
    assert snap.last_success_position is None
    assert snap.last_error_code == "RuntimeError"
    storage.close()


@pytest.mark.asyncio
async def test_non_required_non_transactional_io_failure_does_not_block_required_observer() -> None:
    """非 required trace-like I/O 失败不应阻塞 required observer checkpoint。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))

    required_observer = _RequiredRecordingObserver()
    trace_observer = _FailingNonTransactionalObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(required_observer, trace_observer),
    )
    snapshots = await coord.drain()
    by_observer = {checkpoint.observer_id: checkpoint for checkpoint in snapshots}
    required_checkpoint = by_observer["required_memory_like"]
    trace_checkpoint = by_observer["non_required_trace_like"]
    assert required_checkpoint.status is ObserverStatus.CAUGHT_UP
    assert required_checkpoint.last_success_position is not None
    assert required_checkpoint.last_success_position.value == 1
    assert required_observer.processed_positions == [1]
    assert trace_checkpoint.status is ObserverStatus.BLOCKED_FAILED
    assert trace_checkpoint.last_success_position is None
    assert trace_checkpoint.last_error_code == "non_required_io:OSError"
    assert trace_observer.call_count == 1
    storage.close()


@pytest.mark.asyncio
async def test_non_required_checkpoint_failure_replays_after_sink_success() -> None:
    """非事务 sink 成功但 checkpoint 失败时，下次 drain 应重放同一 batch。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))

    trace_observer = _RecordingNonTransactionalObserver()
    assert isinstance(trace_observer, NonTransactionalObserverSink)
    proj_store = _CheckpointFailOnceProjectionStore(
        storage=storage,
        observer_id=trace_observer.descriptor.observer_id,
    )
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(trace_observer,),
    )
    await coord.initialize()
    failed = await coord.run_once(observer=trace_observer)
    assert failed.status is ObserverStatus.BLOCKED_FAILED
    assert failed.last_success_position is None
    assert failed.last_error_code == "non_required_checkpoint:RuntimeError"
    assert trace_observer.written_batches == [(1,)]

    recovered = await coord.run_once(observer=trace_observer)
    assert recovered.status is ObserverStatus.CAUGHT_UP
    assert recovered.last_success_position is not None
    assert recovered.last_success_position.value == 1
    assert trace_observer.written_batches == [(1,), (1,)]
    storage.close()


@pytest.mark.asyncio
async def test_tool_trace_replay_after_checkpoint_failure_is_analyzer_deduped(
    tmp_path: Path,
) -> None:
    """真实 ToolTraceObserver replay 写出重复行，analyzer 按幂等键去重。

    :param tmp_path: pytest 提供的临时 trace 根目录。
    :returns: 无返回值。
    :raises Exception: 测试装配、EventLog append、projection drain 或 trace 分析失败时抛出。
    """

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_tool_call_requested_draft(run_id="r1", tool_call_id="call-1"))
    await store.append(_tool_call_accepted_draft(run_id="r1", tool_call_id="call-1"))

    trace_observer = ToolTraceObserver(jsonl_sink=ToolTraceJsonlSink(root_path=tmp_path))
    proj_store = _CheckpointFailOnceProjectionStore(
        storage=storage,
        observer_id=trace_observer.descriptor.observer_id,
    )
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(trace_observer,),
    )
    await coord.initialize()

    failed = await coord.run_once(observer=trace_observer)
    first_lines = _read_trace_jsonl_lines(root=tmp_path, session_id="s")
    assert failed.status is ObserverStatus.BLOCKED_FAILED
    assert failed.last_success_position is None
    assert failed.last_error_code == "non_required_checkpoint:RuntimeError"
    assert len(first_lines) == 1

    recovered = await coord.run_once(observer=trace_observer)
    replayed_lines = _read_trace_jsonl_lines(root=tmp_path, session_id="s")
    assert recovered.status is ObserverStatus.CAUGHT_UP
    assert recovered.last_success_position is not None
    assert recovered.last_success_position.value == 2
    assert len(replayed_lines) == 2
    assert replayed_lines[0]["idempotency_key"] == replayed_lines[1]["idempotency_key"]

    report = analyze_trace_root(trace_root=tmp_path)
    assert report.total_lines_read == 2
    assert report.deduped_record_count == 1
    assert report.record_counts_by_type == {"tool_call": 1}
    assert report.duplicate_idempotency_keys == (replayed_lines[0]["idempotency_key"],)
    storage.close()


@pytest.mark.asyncio
async def test_projection_store_advance_regression_rejected() -> None:
    """checkpoint 倒退必须被 ProjectionStore 拒绝。"""

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    proj = ProjectionStore(storage=storage)
    async with storage.transaction() as tx:
        proj.ensure(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
        )
        proj.advance_success(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
            position=GlobalEventPosition(value=10),
            status=ObserverStatus.RUNNING,
        )
    with pytest.raises(ValueError):
        async with storage.transaction() as tx:
            proj.advance_success(
                tx=tx,
                observer_id="x",
                projection_name="y",
                schema_version=1,
                position=GlobalEventPosition(value=5),
                status=ObserverStatus.RUNNING,
            )
    storage.close()


@pytest.mark.asyncio
async def test_projection_lag_events_reflects_remaining_events() -> None:
    """checkpoint 报告的 lag = MAX(position) - last_success_position。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    for idx in range(3):
        await store.append(_content_draft(run_id="r1", idx=idx))

    proj = ProjectionStore(storage=storage)
    async with storage.transaction() as tx:
        proj.ensure(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
        )
        proj.advance_success(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
            position=GlobalEventPosition(value=1),
            status=ObserverStatus.RUNNING,
        )
    cp = proj.get(observer_id="x", projection_name="y", schema_version=1)
    assert cp is not None
    assert cp.lag_events == 2
    storage.close()


@pytest.mark.asyncio
async def test_zero_event_observer_advances_to_caught_up() -> None:
    """零 EventLog + checkpoint position None 时 observer 应推进到 CAUGHT_UP。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    # 不写入任何事件，EventLog 为空。

    observer = AuditProjectionObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(observer,),
    )
    snapshots = await coord.drain()
    assert len(snapshots) == 1
    cp = snapshots[0]
    assert cp.status is ObserverStatus.CAUGHT_UP
    # 零事件时 observer 从 None 推进到 position=0 (初始 caught-up 位置)。
    assert cp.last_success_position is not None
    assert cp.last_success_position.value == 0
    storage.close()
