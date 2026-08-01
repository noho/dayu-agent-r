"""Host transient live stream 的 production-runtime 测试支撑。

本模块提供可控的真实 ``LocalEngineWorker`` 事件流与 durable 快照读取器，
供 Host stress 和 Host→Service→CLI 跨层测试复用。它不替代 Host public
contract，也不在测试侧推导新的业务状态。
"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeAlias, cast

from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    ContentDeltaData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    ReasoningDeltaData,
    ToolCallDeltaData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
)
from tests.host.public_smoke_support import (
    deterministic_runner_spec,
    open_host_options,
)

_OBSERVED_AT = datetime(2026, 7, 21, 2, 3, 4, tzinfo=UTC)

_SQLiteCell: TypeAlias = str | int | float | bytes | None
"""本测试 helper 允许读取的 SQLite cell 类型。"""


@dataclass(frozen=True, slots=True)
class TransientStreamCounts:
    """测试事件流中三类 transient delta 的精确数量。

    :param content: content delta 数量。
    :param reasoning: reasoning delta 数量。
    :param tool_call: tool-call delta 数量。
    """

    content: int
    reasoning: int
    tool_call: int

    def __post_init__(self) -> None:
        """校验三类计数均为非负严格整数。

        :returns: ``None``。
        :raises TypeError: 任一计数不是严格整数时抛出。
        :raises ValueError: 任一计数小于零时抛出。
        """

        for field_name, value in (
            ("content", self.content),
            ("reasoning", self.reasoning),
            ("tool_call", self.tool_call),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"TransientStreamCounts.{field_name} must be int")
            if value < 0:
                raise ValueError(
                    f"TransientStreamCounts.{field_name} must be non-negative"
                )

    @property
    def total(self) -> int:
        """返回三类 delta 总数。

        :returns: 三类计数之和。
        :raises Exception: 本属性不主动抛出异常。
        """

        return self.content + self.reasoning + self.tool_call


@dataclass(frozen=True, slots=True)
class TransientDurableSnapshot:
    """单个测试 Run 的 owner-level durable 终态快照。

    :param run_status: ``host_runs`` 状态。
    :param run_attempt_id: Run 当前 Attempt 标识。
    :param run_terminal_event_id: Run terminal EventLog 标识。
    :param run_terminal_event_sequence: Run terminal EventLog 序号。
    :param attempt_count: Run 对应 Attempt row 数量。
    :param attempt_status: 唯一 Attempt 状态。
    :param attempt_terminal_event_id: Attempt terminal EventLog 标识。
    :param attempt_terminal_event_sequence: Attempt terminal EventLog 序号。
    :param terminal_event_type: terminal EventLog 类型。
    :param terminal_event_id: terminal EventLog 标识。
    :param terminal_event_sequence: terminal EventLog 序号。
    """

    run_status: str
    run_attempt_id: str
    run_terminal_event_id: str
    run_terminal_event_sequence: int
    attempt_count: int
    attempt_status: str
    attempt_terminal_event_id: str
    attempt_terminal_event_sequence: int
    terminal_event_type: str
    terminal_event_id: str
    terminal_event_sequence: int


class TransientStreamWorkerFactory:
    """创建按精确数量输出三类 delta 后成功终止的测试 worker。

    :param counts: 三类 delta 数量。
    :param final_answer: 最终回答正文。
    :param release_event: 可选的 stream 起始 barrier；未 set 前 worker 不发布。
    :param terminal_release_event: 可选的 terminal barrier；delta 完成后等待其 set。
    """

    def __init__(
        self,
        *,
        counts: TransientStreamCounts,
        final_answer: str,
        release_event: asyncio.Event | None = None,
        terminal_release_event: asyncio.Event | None = None,
    ) -> None:
        """初始化可控 worker factory。

        :param counts: 三类 delta 数量。
        :param final_answer: 最终回答正文。
        :param release_event: 可选的 stream 起始 barrier。
        :param terminal_release_event: 可选的 terminal 发布 barrier。
        :returns: 无返回值。
        :raises ValueError: 最终回答为空时抛出。
        """

        if not final_answer:
            raise ValueError("final_answer must be non-empty")
        self.counts = counts
        self.final_answer = final_answer
        self.release_event = release_event
        self.terminal_release_event = terminal_release_event
        self.accepted_event = asyncio.Event()
        self.stream_started_event = asyncio.Event()
        self.deltas_finished_event = asyncio.Event()
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.cancel_reasons: list[str] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建绑定当前 dispatch snapshot 的测试 worker。

        :param snapshot: Host dispatch snapshot。
        :returns: 测试 ``LocalEngineWorker``。
        :raises Exception: 本方法不主动抛出异常。
        """

        del snapshot
        return _TransientStreamWorker(self)


class _TransientStreamWorker:
    """接受 dispatch 并创建 transient stream handle 的测试 worker。"""

    def __init__(self, factory: TransientStreamWorkerFactory) -> None:
        """初始化测试 worker。

        :param factory: 共享 barrier 与观测状态的 factory。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 Host dispatch 并返回真实 EngineEvent stream handle。

        :param snapshot: Host dispatch snapshot。
        :param request: Engine Run 请求。
        :returns: transient stream handle。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_event.set()
        return _TransientStreamHandle(
            snapshot=snapshot,
            request=request,
            factory=self._factory,
        )


class _TransientStreamHandle:
    """按轮次交错发布三类 delta 并提交 final answer 的测试 handle。"""

    def __init__(
        self,
        *,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
        factory: TransientStreamWorkerFactory,
    ) -> None:
        """初始化测试 handle。

        :param snapshot: 当前 Attempt dispatch snapshot。
        :param request: 当前 dispatch 的 Engine request。
        :param factory: 共享配置与 barrier 的 factory。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._snapshot = snapshot
        self._request = request
        self._factory = factory

    @property
    def local_worker_id(self) -> str:
        """返回稳定测试 worker 标识。

        :returns: 测试 worker 标识。
        :raises Exception: 本属性不主动抛出异常。
        """

        return "transient-stream-test-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """按 content/reasoning/tool-call 轮次输出 delta，最后输出 final。

        :returns: EngineEvent 异步迭代器。
        :raises asyncio.CancelledError: 外部取消 stream 时透传。
        """

        if self._factory.release_event is not None:
            await self._factory.release_event.wait()
        self._factory.stream_started_event.set()
        counts = self._factory.counts
        for item_index in range(max(counts.content, counts.reasoning, counts.tool_call)):
            if item_index < counts.content:
                yield _content_delta_event(self._snapshot, item_index)
                await asyncio.sleep(0)
            if item_index < counts.reasoning:
                yield _reasoning_delta_event(self._snapshot, item_index)
                await asyncio.sleep(0)
            if item_index < counts.tool_call:
                yield _tool_call_delta_event(self._snapshot, item_index)
                await asyncio.sleep(0)
        self._factory.deltas_finished_event.set()
        if self._factory.terminal_release_event is not None:
            await self._factory.terminal_release_event.wait()
        yield _final_answer_event(
            self._snapshot,
            request=self._request,
            content=self._factory.final_answer,
        )

    async def close(self) -> None:
        """关闭测试 handle。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录 Host 发出的 Run cancel reason。

        :param reason: Host cancel 原因。
        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._factory.cancel_reasons.append(reason)


def transient_stream_open_host_options(
    tmp_path: pathlib.Path,
    factory: TransientStreamWorkerFactory,
) -> OpenHostOptions:
    """构造 transient production-runtime 测试使用的 Host options。

    :param tmp_path: pytest 临时目录。
    :param factory: transient stream worker factory。
    :returns: 完整 ``OpenHostOptions``。
    :raises TypeError: options 字段非法时由底层构造抛出。
    :raises ValueError: options 组合非法时由底层构造抛出。
    """

    return open_host_options(
        tmp_path,
        runner_spec=deterministic_runner_spec("transient-stream-test-model"),
        worker_factory=factory,
        allow_tool_calls=False,
    )


def event_log_type_count(db_path: pathlib.Path, event_type: str) -> int:
    """读取 EventLog 中指定类型的 row 数量。

    :param db_path: Host SQLite 路径。
    :param event_type: 目标 EventLog 类型。
    :returns: 精确 row 数量。
    :raises AssertionError: SQLite 未返回严格整数时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = cast(
            tuple[_SQLiteCell, ...] | None,
            connection.execute(
                f"SELECT COUNT(*) FROM {TABLE_EVENT_LOG} WHERE event_type = ?",
                (event_type,),
            ).fetchone(),
        )
    return _required_int_cell(row, field_name="event_log_type_count")


def read_transient_durable_snapshot(
    db_path: pathlib.Path,
    *,
    run_id: str,
) -> TransientDurableSnapshot:
    """从 owner tables 读取 Run、Attempt 与 terminal EventLog 同源快照。

    :param db_path: Host SQLite 路径。
    :param run_id: 目标 Run 标识。
    :returns: owner-level durable 终态快照。
    :raises AssertionError: row 缺失、数量错误或字段类型非法时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        run_row = cast(
            tuple[_SQLiteCell, ...] | None,
            connection.execute(
                f"""
                SELECT status, current_attempt_id, terminal_event_id,
                       terminal_event_sequence
                FROM {TABLE_HOST_RUNS}
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone(),
        )
        attempt_rows = cast(
            list[tuple[_SQLiteCell, ...]],
            connection.execute(
                f"""
                SELECT status, terminal_event_id, terminal_event_sequence
                FROM {TABLE_HOST_ATTEMPTS}
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchall(),
        )
        terminal_row = cast(
            tuple[_SQLiteCell, ...] | None,
            connection.execute(
                f"""
                SELECT event_type, event_id, event_sequence
                FROM {TABLE_EVENT_LOG}
                WHERE run_id = ? AND event_type = 'RUN_SUCCEEDED'
                """,
                (run_id,),
            ).fetchone(),
        )
    if run_row is None:
        raise AssertionError("host_runs row is missing")
    if len(attempt_rows) != 1:
        raise AssertionError("expected exactly one host_attempts row")
    if terminal_row is None:
        raise AssertionError("RUN_SUCCEEDED EventLog row is missing")
    attempt_row = attempt_rows[0]
    return TransientDurableSnapshot(
        run_status=_required_str(run_row[0], field_name="run.status"),
        run_attempt_id=_required_str(
            run_row[1], field_name="run.current_attempt_id"
        ),
        run_terminal_event_id=_required_str(
            run_row[2], field_name="run.terminal_event_id"
        ),
        run_terminal_event_sequence=_required_int(
            run_row[3], field_name="run.terminal_event_sequence"
        ),
        attempt_count=len(attempt_rows),
        attempt_status=_required_str(attempt_row[0], field_name="attempt.status"),
        attempt_terminal_event_id=_required_str(
            attempt_row[1], field_name="attempt.terminal_event_id"
        ),
        attempt_terminal_event_sequence=_required_int(
            attempt_row[2], field_name="attempt.terminal_event_sequence"
        ),
        terminal_event_type=_required_str(
            terminal_row[0], field_name="terminal.event_type"
        ),
        terminal_event_id=_required_str(
            terminal_row[1], field_name="terminal.event_id"
        ),
        terminal_event_sequence=_required_int(
            terminal_row[2], field_name="terminal.event_sequence"
        ),
    )


def _content_delta_event(
    snapshot: AttemptDispatchSnapshot,
    item_index: int,
) -> EngineEvent:
    """构造一个 content delta EngineEvent。

    :param snapshot: 当前 Attempt dispatch snapshot。
    :param item_index: delta 索引。
    :returns: content delta EngineEvent。
    :raises ValueError: EngineEvent contract 校验失败时抛出。
    """

    return EngineEvent(
        occurred_at=_OBSERVED_AT,
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.CONTENT_DELTA,
        data=ContentDeltaData(
            iteration_id="iteration-1",
            delta="" if item_index else "content-probe",
        ),
        metadata=None,
    )


def _reasoning_delta_event(
    snapshot: AttemptDispatchSnapshot,
    item_index: int,
) -> EngineEvent:
    """构造一个 reasoning delta EngineEvent。

    :param snapshot: 当前 Attempt dispatch snapshot。
    :param item_index: delta 索引。
    :returns: reasoning delta EngineEvent。
    :raises ValueError: EngineEvent contract 校验失败时抛出。
    """

    return EngineEvent(
        occurred_at=_OBSERVED_AT,
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.REASONING_DELTA,
        data=ReasoningDeltaData(
            iteration_id="iteration-1",
            delta="" if item_index else "slow-consumer-thinking",
        ),
        metadata=None,
    )


def _tool_call_delta_event(
    snapshot: AttemptDispatchSnapshot,
    item_index: int,
) -> EngineEvent:
    """构造一个 tool-call delta EngineEvent。

    :param snapshot: 当前 Attempt dispatch snapshot。
    :param item_index: delta 索引。
    :returns: tool-call delta EngineEvent。
    :raises ValueError: EngineEvent contract 校验失败时抛出。
    """

    return EngineEvent(
        occurred_at=_OBSERVED_AT,
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.TOOL_CALL_DELTA,
        data=ToolCallDeltaData(
            iteration_id="iteration-1",
            tool_call_index=0,
            tool_call_id="tool-call-1",
            name_delta="lookup" if item_index == 0 else None,
            arguments_delta="{}" if item_index == 0 else "",
        ),
        metadata=None,
    )


def _final_answer_event(
    snapshot: AttemptDispatchSnapshot,
    *,
    request: AgentRunRequest,
    content: str,
) -> EngineEvent:
    """构造成功 final answer EngineEvent。

    :param snapshot: 当前 Attempt dispatch snapshot。
    :param request: 当前 dispatch 的 Engine request。
    :param content: 最终回答正文。
    :returns: final answer EngineEvent。
    :raises ValueError: EngineEvent contract 校验失败时抛出。
    """

    return EngineEvent(
        occurred_at=_OBSERVED_AT,
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
            response_identity=_successful_response_identity(request),
        ),
        metadata=None,
    )


def _successful_response_identity(
    request: AgentRunRequest,
) -> SuccessfulRunnerResponseIdentity:
    """构造与 transient worker request 同源的测试响应身份。

    :param request: 当前 worker 实际收到的 Engine request。
    :returns: provider request id 明确不可用的成功响应身份。
    :raises ValueError: request identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider=request.runner_spec.provider,
        effective_model=request.runner_spec.model,
        runner_request_identity=build_runner_request_identity(
            run_id=request.run_id,
            attempt_id=request.attempt_id,
            execution_id=request.execution_id,
            iteration_id=f"{request.run_id}:transient-final",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(
            ProviderRequestIdAvailability.UNAVAILABLE
        ),
        provider_request_id=None,
    )


def _required_int_cell(
    row: tuple[_SQLiteCell, ...] | None,
    *,
    field_name: str,
) -> int:
    """从单 cell SQLite row 读取严格整数。

    :param row: SQLite 查询结果。
    :param field_name: 断言消息使用的字段名。
    :returns: 严格整数。
    :raises AssertionError: row 缺失、cell 数量错误或值不是整数时抛出。
    """

    if row is None or len(row) != 1:
        raise AssertionError(f"{field_name} row is invalid")
    return _required_int(row[0], field_name=field_name)


def _required_int(value: _SQLiteCell, *, field_name: str) -> int:
    """校验 SQLite cell 是严格整数。

    :param value: SQLite cell 值。
    :param field_name: 断言消息使用的字段名。
    :returns: 严格整数。
    :raises AssertionError: 值不是严格整数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{field_name} is not int")
    return value


def _required_str(value: _SQLiteCell, *, field_name: str) -> str:
    """校验 SQLite cell 是非空字符串。

    :param value: SQLite cell 值。
    :param field_name: 断言消息使用的字段名。
    :returns: 非空字符串。
    :raises AssertionError: 值不是非空字符串时抛出。
    """

    if not isinstance(value, str) or not value:
        raise AssertionError(f"{field_name} is not non-empty str")
    return value


__all__: tuple[str, ...] = (
    "TransientDurableSnapshot",
    "TransientStreamCounts",
    "TransientStreamWorkerFactory",
    "event_log_type_count",
    "read_transient_durable_snapshot",
    "transient_stream_open_host_options",
)
