"""Phase 11 recovery 多进程测试支撑。

本模块只服务 ``tests/host`` 下的 recovery multiprocess 测试。它提供
可被 ``multiprocessing`` 启动的顶层 worker target、受控 deterministic
worker factory，以及少量 durable inspection / fault injection helper。
这些 helper 不进入生产代码，不作为 Host recovery truth。
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sqlite3
import time
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC, datetime
from multiprocessing import Process
from typing import cast

from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.host import (
    AttemptDispatchSnapshot,
    HostEventKind,
    HostSessionEvent,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OpenHostOptions,
    RunStatus,
    open_host,
)
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.projection import (
    ProjectionCheckpointRow,
    read_projection_checkpoint,
)
from tests.host.public_smoke_support import (
    deterministic_runner_spec,
    ensure_request,
    followup_request,
    next_terminal_for_run,
    open_host_options,
)

_MARKER_POLL_SECONDS = 0.01
_PROCESS_JOIN_TIMEOUT_SECONDS = 5.0
_RUN_STATUS_POLL_SECONDS = 0.01
_RUN_STATUS_POLL_ATTEMPTS = 300
_LANE_DEFAULT_TIMEOUT_SECONDS = 1.0
_LANE_CLAIM_TTL_SECONDS = 0.4
_LANE_HEARTBEAT_INTERVAL_SECONDS = 0.05
_MISSING_OWNER_PID = 999_999
_HOST_DB_FILENAME = "host.sqlite3"
_ARTIFACT_ROOT_NAME = "artifacts"
_STALE_HEARTBEAT_AT = "2000-01-01T00:00:00.000000Z"
_RUNNING_INSTANCE_STATUS = "running"
_MEMORY_CONSUMER_ID = "host.memory.session.v1"
_INITIAL_CHECKPOINT_SEQUENCE = 0
_NOW_TEXT = "2026-05-19T00:00:00.000000Z"


@dataclass(frozen=True, slots=True)
class AcceptedAttemptMarker:
    """已被 worker accept 的 Attempt 标记。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    """

    session_id: str
    run_id: str
    attempt_id: str


class BlockingFinalAnswerHandle:
    """等待文件释放后才产出 final answer 的 worker handle。

    :param snapshot: 当前 dispatch snapshot。
    :param release_marker: 父进程用于释放 final answer 的文件。
    :param content_prefix: final answer 内容前缀。
    """

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        release_marker: pathlib.Path,
        content_prefix: str,
    ) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_marker: 释放事件文件。
        :param content_prefix: final answer 内容前缀。
        :returns: ``None``。
        :raises ValueError: ``content_prefix`` 为空时抛出。
        """

        if content_prefix.strip() == "":
            raise ValueError("content_prefix must be non-empty")
        self._snapshot = snapshot
        self._release_marker = release_marker
        self._content_prefix = content_prefix

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: worker id。
        """

        return "phase11-slice5-blocking-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待 release marker 后产出 final answer。

        :returns: EngineEvent 异步迭代器。
        """

        while not self._release_marker.exists():
            await asyncio.sleep(_MARKER_POLL_SECONDS)
        yield EngineEvent(
            occurred_at=datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=f"{self._content_prefix}:{self._snapshot.run_id}",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class BlockingFinalAnswerWorker:
    """写入 accepted marker 后返回受控 final answer handle。

    :param factory: 所属 worker factory。
    """

    def __init__(self, factory: "BlockingFinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并记录 accepted marker。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 受控 final answer handle。
        """

        del request
        write_accepted_marker(
            self._factory.accepted_marker,
            AcceptedAttemptMarker(
                session_id=snapshot.session_id,
                run_id=snapshot.run_id,
                attempt_id=snapshot.attempt_id,
            ),
        )
        return BlockingFinalAnswerHandle(
            snapshot,
            self._factory.release_marker,
            self._factory.content_prefix,
        )


class BlockingFinalAnswerWorkerFactory:
    """可跨进程构造的受控 final answer worker factory。

    :param accepted_marker: worker accept 后写入的 marker 文件。
    :param release_marker: 控制 final answer 释放的 marker 文件。
    :param content_prefix: final answer 内容前缀。
    """

    def __init__(
        self,
        accepted_marker: pathlib.Path,
        release_marker: pathlib.Path,
        content_prefix: str,
    ) -> None:
        """初始化 factory。

        :param accepted_marker: accepted marker 文件。
        :param release_marker: release marker 文件。
        :param content_prefix: final answer 内容前缀。
        :returns: ``None``。
        """

        self.accepted_marker = accepted_marker
        self.release_marker = release_marker
        self.content_prefix = content_prefix

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建受控 worker。

        :param snapshot: dispatch snapshot，本 factory 不直接读取。
        :returns: 受控 worker。
        """

        del snapshot
        return BlockingFinalAnswerWorker(self)


class AsyncControlledFinalAnswerHandle:
    """由当前事件循环 ``asyncio.Event`` 控制的 final answer handle。

    :param snapshot: 当前 dispatch snapshot。
    :param release_event: 释放 final answer 的事件。
    :param content_prefix: final answer 内容前缀。
    """

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        release_event: asyncio.Event,
        content_prefix: str,
    ) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_event: 释放事件。
        :param content_prefix: final answer 内容前缀。
        :returns: ``None``。
        """

        self._snapshot = snapshot
        self._release_event = release_event
        self._content_prefix = content_prefix

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: worker id。
        """

        return "phase11-slice5-controlled-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待事件释放后产出 final answer。

        :returns: EngineEvent 异步迭代器。
        """

        await self._release_event.wait()
        yield EngineEvent(
            occurred_at=datetime(2026, 5, 19, 0, 0, 1, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=f"{self._content_prefix}:{self._snapshot.run_id}",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class AsyncControlledFinalAnswerWorker:
    """记录 accepted snapshot 并返回事件受控 handle。

    :param factory: 所属 factory。
    """

    def __init__(self, factory: "AsyncControlledFinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并记录 snapshot。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 事件受控 handle。
        """

        del request
        self._factory.snapshots.append(snapshot)
        self._factory.accepted_event.set()
        return AsyncControlledFinalAnswerHandle(
            snapshot,
            self._factory.release_event,
            self._factory.content_prefix,
        )


class AsyncControlledFinalAnswerWorkerFactory:
    """当前进程内使用的事件受控 final answer worker factory。

    :param content_prefix: final answer 内容前缀。
    """

    def __init__(self, content_prefix: str) -> None:
        """初始化 factory。

        :param content_prefix: final answer 内容前缀。
        :returns: ``None``。
        """

        self.content_prefix = content_prefix
        self.accepted_event = asyncio.Event()
        self.release_event = asyncio.Event()
        self.snapshots: list[AttemptDispatchSnapshot] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建事件受控 worker。

        :param snapshot: dispatch snapshot，本 factory 不直接读取。
        :returns: 事件受控 worker。
        """

        del snapshot
        return AsyncControlledFinalAnswerWorker(self)


def recovery_open_host_options(
    root_path: pathlib.Path,
    worker_factory: LocalEngineWorkerFactory,
) -> OpenHostOptions:
    """构造 Slice 5 多进程测试共用 OpenHostOptions。

    :param root_path: 测试根目录。
    :param worker_factory: 本进程使用的 worker factory。
    :returns: OpenHostOptions。
    """

    options = open_host_options(
        root_path,
        runner_spec=deterministic_runner_spec("phase11-slice5"),
        worker_factory=worker_factory,
        allow_tool_calls=False,
    )
    return replace(
        options,
        lane_default_timeout_seconds=_LANE_DEFAULT_TIMEOUT_SECONDS,
        lane_claim_ttl_seconds=_LANE_CLAIM_TTL_SECONDS,
        lane_heartbeat_interval_seconds=_LANE_HEARTBEAT_INTERVAL_SECONDS,
    )


def run_blocking_owner_process(
    root_path_text: str,
    accepted_marker_text: str,
    release_marker_text: str,
    result_marker_text: str,
    slot_key: str,
    client_request_id: str,
    user_prompt: str,
) -> None:
    """多进程 owner target：打开 Host、提交 Run，并在 release 前阻塞 final。

    :param root_path_text: 测试根目录文本路径。
    :param accepted_marker_text: accepted marker 文本路径。
    :param release_marker_text: release marker 文本路径。
    :param result_marker_text: result marker 文本路径。
    :param slot_key: ensure_session slot key。
    :param client_request_id: follow-up 幂等 id。
    :param user_prompt: 用户输入。
    :returns: ``None``。
    """

    asyncio.run(
        _run_blocking_owner_async(
            root_path=pathlib.Path(root_path_text),
            accepted_marker=pathlib.Path(accepted_marker_text),
            release_marker=pathlib.Path(release_marker_text),
            result_marker=pathlib.Path(result_marker_text),
            slot_key=slot_key,
            client_request_id=client_request_id,
            user_prompt=user_prompt,
        )
    )


def run_open_probe_process(root_path_text: str, result_marker_text: str) -> None:
    """多进程 probe target：只打开同一个 durable store 后立即关闭。

    :param root_path_text: 测试根目录文本路径。
    :param result_marker_text: result marker 文本路径。
    :returns: ``None``。
    """

    asyncio.run(
        _run_open_probe_async(
            root_path=pathlib.Path(root_path_text),
            result_marker=pathlib.Path(result_marker_text),
        )
    )


async def _run_blocking_owner_async(
    *,
    root_path: pathlib.Path,
    accepted_marker: pathlib.Path,
    release_marker: pathlib.Path,
    result_marker: pathlib.Path,
    slot_key: str,
    client_request_id: str,
    user_prompt: str,
) -> None:
    """执行 owner process 的 async 主体。

    :param root_path: 测试根目录。
    :param accepted_marker: accepted marker 文件。
    :param release_marker: release marker 文件。
    :param result_marker: result marker 文件。
    :param slot_key: ensure_session slot key。
    :param client_request_id: follow-up 幂等 id。
    :param user_prompt: 用户输入。
    :returns: ``None``。
    """

    factory = BlockingFinalAnswerWorkerFactory(
        accepted_marker=accepted_marker,
        release_marker=release_marker,
        content_prefix="owner-final",
    )
    options = recovery_open_host_options(root_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(ensure_request(slot_key))
        watcher = await host.watch_session_events(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    client_request_id,
                    user_prompt,
                ),
            )
            terminal = await next_terminal_for_run(watcher, followup.accepted_run_id)
            write_result_marker(
                result_marker,
                f"{terminal.kind.value}\n{terminal.run_id or ''}\n",
            )
        finally:
            await close_host_event_iterator(watcher)


async def _run_open_probe_async(
    *,
    root_path: pathlib.Path,
    result_marker: pathlib.Path,
) -> None:
    """执行 open probe process 的 async 主体。

    :param root_path: 测试根目录。
    :param result_marker: result marker 文件。
    :returns: ``None``。
    """

    release_marker = root_path / "probe-release"
    accepted_marker = root_path / "probe-accepted"
    factory = BlockingFinalAnswerWorkerFactory(
        accepted_marker=accepted_marker,
        release_marker=release_marker,
        content_prefix="probe-final",
    )
    async with open_host(recovery_open_host_options(root_path, factory)):
        write_result_marker(result_marker, "opened\n")
        await asyncio.sleep(_MARKER_POLL_SECONDS)


async def close_host_event_iterator(
    iterator: AsyncIterator[HostSessionEvent],
) -> None:
    """关闭测试持有的 Host 联合事件 async generator。

    :param iterator: Host durable/transient 联合事件 iterator。
    :returns: ``None``。
    :raises Exception: 底层 async generator close 失败时透传。
    """

    await cast(AsyncGenerator[HostSessionEvent, None], iterator).aclose()


async def wait_for_run_status(
    options: OpenHostOptions,
    run_id: str,
    expected_status: RunStatus,
) -> None:
    """通过 public Host handle 等待 Run 到达指定状态。

    :param options: OpenHostOptions。
    :param run_id: Run id。
    :param expected_status: 目标状态。
    :returns: ``None``。
    :raises AssertionError: 超时仍未到达目标状态时抛出。
    """

    factory = AsyncControlledFinalAnswerWorkerFactory("status-helper")
    async with open_host(recovery_open_host_options(options.db_path.parent, factory)) as host:
        for _ in range(_RUN_STATUS_POLL_ATTEMPTS):
            snapshot = await host.get_run(run_id)
            if snapshot.status is expected_status:
                return
            await asyncio.sleep(_RUN_STATUS_POLL_SECONDS)
    raise AssertionError(f"run {run_id} did not reach {expected_status.value}")


def wait_for_accepted_marker(path: pathlib.Path, timeout_seconds: float) -> AcceptedAttemptMarker:
    """等待并读取 accepted marker。

    :param path: marker 文件路径。
    :param timeout_seconds: 超时秒数。
    :returns: accepted marker。
    :raises TimeoutError: 超时未出现 marker 时抛出。
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return read_accepted_marker(path)
        time.sleep(_MARKER_POLL_SECONDS)
    raise TimeoutError(f"accepted marker not written: {path}")


def write_accepted_marker(path: pathlib.Path, marker: AcceptedAttemptMarker) -> None:
    """写入 accepted marker。

    :param path: marker 文件路径。
    :param marker: marker 内容。
    :returns: ``None``。
    """

    write_result_marker(
        path,
        f"{marker.session_id}\n{marker.run_id}\n{marker.attempt_id}\n",
    )


def read_accepted_marker(path: pathlib.Path) -> AcceptedAttemptMarker:
    """读取 accepted marker。

    :param path: marker 文件路径。
    :returns: accepted marker。
    :raises AssertionError: marker 格式不完整时抛出。
    """

    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3:
        raise AssertionError("accepted marker is incomplete")
    return AcceptedAttemptMarker(
        session_id=lines[0],
        run_id=lines[1],
        attempt_id=lines[2],
    )


def write_result_marker(path: pathlib.Path, content: str) -> None:
    """原子写入测试 marker。

    :param path: marker 文件路径。
    :param content: marker 内容。
    :returns: ``None``。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    os.replace(temporary_path, path)


def terminate_process(process: Process) -> None:
    """终止并 join 测试子进程。

    :param process: 待终止进程。
    :returns: ``None``。
    :raises AssertionError: 进程未能退出时抛出。
    """

    if process.is_alive():
        process.terminate()
    process.join(_PROCESS_JOIN_TIMEOUT_SECONDS)
    if process.is_alive():
        raise AssertionError("process did not terminate")


def wait_for_runtime_lane_claim_ttl_to_expire() -> None:
    """等待测试 lane claim TTL 过期。

    该等待只服务 runtime capacity cleanup，不参与 Host recovery proof。

    :returns: ``None``。
    """

    time.sleep(_LANE_CLAIM_TTL_SECONDS + _LANE_HEARTBEAT_INTERVAL_SECONDS)


def force_owner_pid_missing_and_heartbeat_stale(
    root_path: pathlib.Path,
    run_id: str,
) -> None:
    """fault-injection-only：改写当前 dispatch owner 为 pid missing + stale heartbeat。

    本 helper 是 tests/host recovery 故障注入 owner，不是 liveness 语义真源。
    生产 liveness API 不应制造 pid missing / stale heartbeat 状态。

    :param root_path: 测试根目录。
    :param run_id: 目标 Run id。
    :returns: ``None``。
    :raises AssertionError: 未找到当前 owner row 时抛出。
    """

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        cursor = connection.execute(
            """
            UPDATE host_instances
            SET pid = ?, heartbeat_at = ?, status = ?
            WHERE host_instance_id = (
              SELECT dispatch.owner_host_instance_id
              FROM host_runs AS run
              JOIN host_attempt_dispatch_records AS dispatch
                ON dispatch.attempt_id = run.current_attempt_id
              WHERE run.run_id = ?
            )
            """,
            (
                _MISSING_OWNER_PID,
                _STALE_HEARTBEAT_AT,
                _RUNNING_INSTANCE_STATUS,
                run_id,
            ),
        )
        connection.commit()
    if cursor.rowcount != 1:
        raise AssertionError("owner host instance was not updated")


def force_memory_projection_lag(root_path: pathlib.Path) -> None:
    """fault-injection-only：制造 memory projection checkpoint lag。

    本 helper 是 tests/host recovery 故障注入 owner，不是 checkpoint 语义真源。
    生产 checkpoint helper 只初始化或单调推进 checkpoint，不提供把既有
    checkpoint 倒退并清空 ``checkpoint_event_id`` 的接口。

    :param root_path: 测试根目录。
    :returns: ``None``。
    """

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        connection.execute(
            """
            INSERT INTO host_projection_checkpoints (
              consumer_id,
              checkpoint_event_sequence,
              checkpoint_event_id,
              last_success_at,
              updated_at
            ) VALUES (?, ?, NULL, NULL, ?)
            ON CONFLICT(consumer_id) DO UPDATE SET
              checkpoint_event_sequence = excluded.checkpoint_event_sequence,
              checkpoint_event_id = NULL,
              last_success_at = NULL,
              updated_at = excluded.updated_at
            """,
            (_MEMORY_CONSUMER_ID, _INITIAL_CHECKPOINT_SEQUENCE, _NOW_TEXT),
        )
        connection.commit()


def event_type_count(root_path: pathlib.Path, event_type: str) -> int:
    """diagnostic-only：统计 EventLog 中指定事件类型的跨 Run 数量。

    本 helper 只服务 recovery 测试同步与失败定位，是 point-in-time diagnostic，
    不是 EventLog truth。生产 run-scoped event count helper 不是该跨 Run
    聚合读取的精确等价物。

    :param root_path: 测试根目录。
    :param event_type: event_type。
    :returns: 事件数量。
    :raises TypeError: SQLite COUNT 结果类型不符合预期时抛出。
    """

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
            (event_type,),
        ).fetchone()
    if row is None:
        return 0
    value = row[0]
    if not isinstance(value, int):
        raise TypeError("event count must be int")
    return value


def attempt_count_for_run(root_path: pathlib.Path, run_id: str) -> int:
    """统计指定 Run 的 Attempt 数。

    :param root_path: 测试根目录。
    :param run_id: Run id。
    :returns: Attempt 数。
    """

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM host_attempts WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return 0
    value = row[0]
    if not isinstance(value, int):
        raise TypeError("attempt count must be int")
    return value


def current_attempt_id_for_run(root_path: pathlib.Path, run_id: str) -> str:
    """读取指定 Run 的 current_attempt_id。

    :param root_path: 测试根目录。
    :param run_id: Run id。
    :returns: current Attempt id。
    :raises AssertionError: Run 不存在或 current_attempt_id 为空时抛出。
    """

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        row = connection.execute(
            "SELECT current_attempt_id FROM host_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None or not isinstance(row[0], str) or row[0].strip() == "":
        raise AssertionError("current attempt id is missing")
    return row[0]


def projection_checkpoint_sequence(root_path: pathlib.Path) -> int | None:
    """通过 production owner helper 读取 memory projection checkpoint sequence。

    :param root_path: 测试根目录。
    :returns: checkpoint sequence；row 不存在时返回 ``None``。
    :raises Exception: durable store 打开或 read transaction 失败时透传。
    """

    durable_options = HostDurableStoreOptions(
        db_path=root_path / _HOST_DB_FILENAME,
        payload_policy=PayloadStoragePolicy(artifact_root=root_path / _ARTIFACT_ROOT_NAME),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )
    row: ProjectionCheckpointRow | None = None
    with open_host_durable_store(durable_options) as store:
        row = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID)
        )
    if row is None:
        return None
    return row.checkpoint_event_sequence


def assert_process_exited_successfully(process: Process) -> None:
    """断言子进程成功退出。

    :param process: 子进程。
    :returns: ``None``。
    :raises AssertionError: 子进程仍存活或退出码非零时抛出。
    """

    process.join(_PROCESS_JOIN_TIMEOUT_SECONDS)
    if process.is_alive():
        raise AssertionError("process is still alive")
    if process.exitcode != 0:
        raise AssertionError(f"process failed with exit code {process.exitcode}")
