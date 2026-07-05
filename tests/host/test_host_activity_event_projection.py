"""WU-CLI-ACTIVITY-01 Slice A Host activity event projection 测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator, Mapping
from typing import cast

import pytest

import dayu.host.read_api as read_api
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import (
    ToolBundle,
    ToolDefinition,
    ToolDisplayInfo,
)
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
from dayu.contracts.tool_outcome import ToolExecutionOutcome
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    EnsureSessionRequest,
    FollowupBehavior,
    HostActivityKind,
    HostActivitySeverity,
    HostActivityStatus,
    HostCallContext,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostToolingOptions,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.durable.codec import canonical_json_dumps
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.state import read_run_by_id
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import default_memory_projection_policy
from dayu.host.payload_resolution import event_payload_object
from dayu.host.read_api import _host_event_from_row

_SESSION_SLOT = "activity-session"


class _BlockingHandle:
    """测试用阻塞 worker handle。"""

    def __init__(self, release: asyncio.Event) -> None:
        """初始化 handle。

        :param release: 释放 Engine event stream 的事件。
        :returns: ``None``。
        """

        self._release = release

    @property
    def local_worker_id(self) -> str:
        """返回测试 worker id。

        :returns: worker id。
        """

        return "activity-projection-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待释放后结束空 EngineEvent stream。

        :returns: EngineEvent async iterator。
        """

        await self._release.wait()
        if False:
            yield cast(EngineEvent, "unreachable")

    async def close(self) -> None:
        """关闭测试 worker。

        :returns: ``None``。
        """

        self._release.set()

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason
        self._release.set()


class _BlockingWorker:
    """测试用阻塞 worker。"""

    def __init__(self, release: asyncio.Event) -> None:
        """初始化 worker。

        :param release: 释放 Engine event stream 的事件。
        :returns: ``None``。
        """

        self._release = release

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并返回阻塞 handle。

        :param snapshot: dispatch 快照。
        :param request: Engine request。
        :returns: 阻塞 worker handle。
        """

        del snapshot, request
        return _BlockingHandle(self._release)


class _BlockingWorkerFactory:
    """测试用阻塞 worker factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.release = asyncio.Event()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建测试 worker。

        :param snapshot: dispatch 快照。
        :returns: 测试 worker。
        """

        del snapshot
        return _BlockingWorker(self.release)


class _Tool:
    """测试用工具 callable。"""

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """拒绝实际执行测试工具。

        :param call: 工具调用请求。
        :param context: 批式执行上下文。
        :returns: 不返回；测试不会执行该 callable。
        :raises RuntimeError: 测试误执行工具时抛出。
        """

        del call, context
        raise RuntimeError("activity projection test tool must not execute")


class _MissingEventLogStore:
    """测试用缺失 input event 的 EventLogStore 替身。"""

    def read_event_by_id(
        self, transaction: HostTransaction, event_id: str
    ) -> EventLogRow | None:
        """模拟 EventLog 查不到 input event。

        :param transaction: Host transaction。
        :param event_id: event id。
        :returns: 固定返回 ``None``。
        """

        del transaction, event_id
        return None


@pytest.mark.asyncio
async def test_tool_activity_uses_admission_display_snapshot(
    tmp_path: pathlib.Path,
) -> None:
    """工具 activity 从 USER_INPUT_ACCEPTED snapshot 读取展示名。"""

    factory = _BlockingWorkerFactory()
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        accepted = await host.submit_followup(
            session.session_id,
            _followup(
                session.session_id,
                client_request_id="display-snapshot",
                tool_names=frozenset({"lookup_filing"}),
            ),
        )
        event = _project_event(
            tmp_path,
            _row(
                event_id="event-tool-call",
                event_class=EventClass.PREVIEW,
                session_id=session.session_id,
                run_id=accepted.accepted_run_id,
                event_type="TOOL_CALL_REQUESTED",
                payload={
                    "tool_name": "lookup_filing",
                    "argument_key_count": 2,
                },
            ),
        )
        input_payload = _input_payload_for_run(tmp_path, accepted.accepted_run_id)

    activity = event.activity
    assert event.kind is HostEventKind.PROGRESS
    assert event.event_class is HostEventClass.PREVIEW
    assert event.event_type == "TOOL_CALL_REQUESTED"
    assert activity is not None
    assert activity.kind is HostActivityKind.TOOL_CALL
    assert activity.status is HostActivityStatus.STARTED
    assert activity.tool_name == "lookup_filing"
    assert activity.tool_display_name == "查财报"
    assert activity.summary == "参数字段数：2"
    tool_set = input_payload["effective_tool_set"]
    assert isinstance(tool_set, Mapping)
    display_names = tool_set["effective_tool_display_names"]
    assert display_names == {"lookup_filing": "查财报"}


@pytest.mark.asyncio
async def test_tool_activity_falls_back_to_stable_name_without_display(
    tmp_path: pathlib.Path,
) -> None:
    """缺少 display metadata 的 selected tool fallback 稳定工具名。"""

    factory = _BlockingWorkerFactory()
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        accepted = await host.submit_followup(
            session.session_id,
            _followup(
                session.session_id,
                client_request_id="display-fallback",
                tool_names=frozenset({"raw_lookup"}),
            ),
        )
        event = _project_event(
            tmp_path,
            _row(
                event_id="event-tool-fallback",
                event_class=EventClass.PREVIEW,
                session_id=session.session_id,
                run_id=accepted.accepted_run_id,
                event_type="TOOL_CALL_REQUESTED",
                payload={"tool_name": "raw_lookup"},
            ),
        )
        input_payload = _input_payload_for_run(tmp_path, accepted.accepted_run_id)

    activity = event.activity
    assert activity is not None
    assert activity.tool_name == "raw_lookup"
    assert activity.tool_display_name == "raw_lookup"
    tool_set = input_payload["effective_tool_set"]
    assert isinstance(tool_set, Mapping)
    assert tool_set["effective_tool_display_names"] == {}


def test_tool_result_and_batch_activity_projection(tmp_path: pathlib.Path) -> None:
    """tool result / batch done 投影 status、severity 与 counts。"""

    result_event = _project_event(
        tmp_path,
        _row(
            event_id="event-tool-result",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id="run-direct",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_name": "lookup_filing",
                "outcome_kind": "failed",
            },
        ),
    )
    batch_event = _project_event(
        tmp_path,
        _row(
            event_id="event-tool-batch",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id="run-direct",
            event_type="TOOL_CALLS_BATCH_DONE",
            payload={
                "tool_call_count": 3,
                "completed_count": 1,
                "failed_count": 1,
                "cancelled_count": 1,
            },
        ),
    )

    result_activity = result_event.activity
    assert result_activity is not None
    assert result_activity.kind is HostActivityKind.TOOL_RESULT
    assert result_activity.status is HostActivityStatus.FAILED
    assert result_activity.severity is HostActivitySeverity.ERROR
    assert result_activity.tool_display_name == "lookup_filing"
    batch_activity = batch_event.activity
    assert batch_activity is not None
    assert batch_activity.kind is HostActivityKind.TOOL_BATCH
    assert batch_activity.counts is not None
    assert batch_activity.counts.total == 3
    assert batch_activity.counts.completed == 1
    assert batch_activity.counts.failed == 1
    assert batch_activity.counts.cancelled == 1


def test_tool_result_completed_and_cancelled_outcomes(
    tmp_path: pathlib.Path,
) -> None:
    """TOOL_RESULT_ACCEPTED completed / cancelled outcome 映射正确。"""

    completed = _project_event(
        tmp_path,
        _row(
            event_id="event-tool-result-completed",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id="run-direct",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_name": "lookup_filing",
                "outcome_kind": "completed",
            },
        ),
    )
    cancelled = _project_event(
        tmp_path,
        _row(
            event_id="event-tool-result-cancelled",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id="run-direct",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_name": "lookup_filing",
                "outcome_kind": "cancelled",
            },
        ),
    )

    completed_activity = completed.activity
    assert completed_activity is not None
    assert completed_activity.status is HostActivityStatus.COMPLETED
    assert completed_activity.severity is HostActivitySeverity.INFO
    assert completed_activity.summary == "结果状态：completed"
    cancelled_activity = cancelled.activity
    assert cancelled_activity is not None
    assert cancelled_activity.status is HostActivityStatus.CANCELLED
    assert cancelled_activity.severity is HostActivitySeverity.WARNING
    assert cancelled_activity.summary == "结果状态：cancelled"


def test_tool_awaiting_and_run_waiting_activity_projection(
    tmp_path: pathlib.Path,
) -> None:
    """TOOL_AWAITING / RUN_WAITING 投影等待 activity。"""

    tool_awaiting = _project_event(
        tmp_path,
        _row(
            event_id="event-tool-awaiting",
            event_class=EventClass.CANONICAL_FACT,
            session_id="session-direct",
            run_id="run-direct",
            event_type="TOOL_AWAITING",
            payload={
                "tool_name": "lookup_filing",
                "wait_id": "wait-1",
            },
        ),
    )
    run_waiting = _project_event(
        tmp_path,
        _row(
            event_id="event-run-waiting",
            event_class=EventClass.CANONICAL_FACT,
            session_id="session-direct",
            run_id="run-direct",
            event_type="RUN_WAITING",
            payload={"wait_id": "wait-1"},
        ),
    )

    tool_activity = tool_awaiting.activity
    assert tool_activity is not None
    assert tool_activity.kind is HostActivityKind.TOOL_AWAITING
    assert tool_activity.status is HostActivityStatus.WAITING
    assert tool_activity.title == "等待工具完成：lookup_filing"
    assert tool_activity.tool_name == "lookup_filing"
    assert tool_activity.tool_display_name == "lookup_filing"
    run_activity = run_waiting.activity
    assert run_activity is not None
    assert run_activity.kind is HostActivityKind.TOOL_AWAITING
    assert run_activity.status is HostActivityStatus.WAITING
    assert run_activity.title == "等待工具完成"
    assert run_activity.tool_name is None
    assert run_activity.tool_display_name is None


def test_context_compaction_activity_projection(tmp_path: pathlib.Path) -> None:
    """context compaction allowlist 的四类 event 映射正确。"""

    cases = (
        (
            "CONTEXT_COMPACTION_REQUESTED",
            HostActivityStatus.STARTED,
            HostActivitySeverity.INFO,
            "上下文压缩开始",
            None,
        ),
        (
            "CONTEXT_COMPACTED",
            HostActivityStatus.COMPLETED,
            HostActivitySeverity.INFO,
            "上下文压缩完成",
            None,
        ),
        (
            "CONTEXT_COMPACTION_FAILED",
            HostActivityStatus.FAILED,
            HostActivitySeverity.ERROR,
            "上下文压缩失败",
            "quality_check_failed",
        ),
        (
            "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
            HostActivityStatus.FAILED,
            HostActivitySeverity.WARNING,
            "上下文压缩未接受",
            "budget_still_over_limit",
        ),
    )

    for event_type, status, severity, title, failure_reason in cases:
        payload: dict[str, JsonValue] = {}
        if failure_reason is not None:
            payload["failure_reason"] = failure_reason
        event = _project_event(
            tmp_path,
            _row(
                event_id=f"event-{event_type.lower()}",
                event_class=EventClass.CANONICAL_FACT,
                session_id="session-direct",
                run_id="run-direct",
                event_type=event_type,
                payload=payload,
            ),
        )

        activity = event.activity
        assert activity is not None
        assert activity.kind is HostActivityKind.CONTEXT_COMPACTION
        assert activity.status is status
        assert activity.severity is severity
        assert activity.title == title
        assert activity.summary == failure_reason


def test_non_terminal_run_lifecycle_activity_projection(
    tmp_path: pathlib.Path,
) -> None:
    """RUN_ACCEPTED / RUN_STARTED 等非终态 lifecycle 投影 activity。"""

    accepted = _project_event(
        tmp_path,
        _row(
            event_id="event-run-accepted",
            event_class=EventClass.CANONICAL_FACT,
            session_id="session-direct",
            run_id="run-direct",
            event_type="RUN_ACCEPTED",
            payload={},
        ),
    )
    started = _project_event(
        tmp_path,
        _row(
            event_id="event-run-started",
            event_class=EventClass.CANONICAL_FACT,
            session_id="session-direct",
            run_id="run-direct",
            event_type="RUN_STARTED",
            payload={},
        ),
    )

    accepted_activity = accepted.activity
    assert accepted_activity is not None
    assert accepted.kind is HostEventKind.PROGRESS
    assert accepted_activity.kind is HostActivityKind.RUN_LIFECYCLE
    assert accepted_activity.status is HostActivityStatus.STARTED
    assert accepted_activity.title == "运行已接受"
    started_activity = started.activity
    assert started_activity is not None
    assert started.kind is HostEventKind.PROGRESS
    assert started_activity.kind is HostActivityKind.RUN_LIFECYCLE
    assert started_activity.status is HostActivityStatus.IN_PROGRESS
    assert started_activity.title == "运行已开始"


def test_provider_protocol_error_activity_is_bounded(tmp_path: pathlib.Path) -> None:
    """provider diagnostic activity 不暴露 raw payload ref。"""

    event = _project_event(
        tmp_path,
        _row(
            event_id="event-provider-error",
            event_class=EventClass.DIAGNOSTIC,
            session_id="session-direct",
            run_id="run-direct",
            event_type="PROVIDER_PROTOCOL_ERROR",
            payload={
                "error_code": "invalid_stream",
                "message": "bad stream " * 40,
                "raw_payload_ref": "payload-secret-ref",
            },
        ),
    )

    activity = event.activity
    assert activity is not None
    assert activity.kind is HostActivityKind.PROVIDER_DIAGNOSTIC
    assert activity.severity is HostActivitySeverity.WARNING
    assert activity.summary is not None
    assert "invalid_stream" in activity.summary
    assert "payload-secret-ref" not in activity.summary
    assert len(activity.summary) <= 180


@pytest.mark.parametrize(
    ("message", "expected_summary"),
    (
        ("", None),
        ("   \n\t  ", None),
        ("x" * 180, "x" * 180),
        ("x" * 181, ("x" * 179) + "…"),
    ),
)
def test_bounded_summary_boundaries(
    tmp_path: pathlib.Path, message: str, expected_summary: str | None
) -> None:
    """provider diagnostic summary 覆盖空白与边界截断。"""

    event = _project_event(
        tmp_path,
        _row(
            event_id=f"event-provider-boundary-{len(message)}",
            event_class=EventClass.DIAGNOSTIC,
            session_id="session-direct",
            run_id="run-direct",
            event_type="PROVIDER_PROTOCOL_ERROR",
            payload={"message": message},
        ),
    )

    activity = event.activity
    assert activity is not None
    assert activity.summary == expected_summary


def test_activity_descriptor_read_degrades_to_no_activity(
    tmp_path: pathlib.Path,
) -> None:
    """activity payload descriptor 缺失时保留 identity 并降级 activity=None。"""

    event = _project_event(
        tmp_path,
        _row(
            event_id="event-tool-call-missing-descriptor",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id="run-direct",
            event_type="TOOL_CALL_REQUESTED",
            payload={"tool_name": "lookup_filing"},
            payload_ref="payload-missing-activity",
            payload_digest="sha256:"
            "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        ),
    )

    assert event.kind is HostEventKind.PROGRESS
    assert event.event_type == "TOOL_CALL_REQUESTED"
    assert event.activity is None


@pytest.mark.asyncio
async def test_tool_display_fallback_chain_for_missing_snapshot_parts(
    tmp_path: pathlib.Path,
) -> None:
    """display lookup 在 run/payload/mapping 缺失时 fallback 稳定工具名。"""

    factory = _BlockingWorkerFactory()
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        accepted = await host.submit_followup(
            session.session_id,
            _followup(
                session.session_id,
                client_request_id="display-chain",
                tool_names=frozenset({"lookup_filing"}),
            ),
        )

    missing_run = _project_tool_call(tmp_path, "run-missing")
    _replace_input_payload_for_run(
        tmp_path,
        accepted.accepted_run_id,
        {"effective_tool_set": "corrupted"},
    )
    tool_set_not_mapping = _project_tool_call(tmp_path, accepted.accepted_run_id)
    _replace_input_payload_for_run(
        tmp_path,
        accepted.accepted_run_id,
        {"effective_tool_set": {"effective_tool_display_names": "corrupted"}},
    )
    display_names_not_mapping = _project_tool_call(tmp_path, accepted.accepted_run_id)
    _replace_input_payload_for_run(
        tmp_path,
        accepted.accepted_run_id,
        {
            "effective_tool_set": {
                "effective_tool_display_names": {"lookup_filing": ""}
            }
        },
    )
    empty_display_name = _project_tool_call(tmp_path, accepted.accepted_run_id)

    for event in (
        missing_run,
        tool_set_not_mapping,
        display_names_not_mapping,
        empty_display_name,
    ):
        activity = event.activity
        assert activity is not None
        assert activity.tool_name == "lookup_filing"
        assert activity.tool_display_name == "lookup_filing"


@pytest.mark.asyncio
async def test_tool_display_fallback_when_input_event_missing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """display lookup 读不到 input event 时 fallback 稳定工具名。"""

    factory = _BlockingWorkerFactory()
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        accepted = await host.submit_followup(
            session.session_id,
            _followup(
                session.session_id,
                client_request_id="display-input-missing",
                tool_names=frozenset({"lookup_filing"}),
            ),
        )

    monkeypatch.setattr(read_api, "_EVENT_LOG_STORE", _MissingEventLogStore())
    event = _project_tool_call(tmp_path, accepted.accepted_run_id)

    activity = event.activity
    assert activity is not None
    assert activity.tool_name == "lookup_filing"
    assert activity.tool_display_name == "lookup_filing"


def test_delta_and_unknown_events_keep_identity_without_activity(
    tmp_path: pathlib.Path,
) -> None:
    """delta 与未知非终态事件保留 identity 且不投影 raw activity。"""

    content = _project_event(
        tmp_path,
        _row(
            event_id="event-content-delta",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id="run-direct",
            event_type="CONTENT_DELTA",
            payload={"delta": "raw model content"},
        ),
    )
    reasoning = _project_event(
        tmp_path,
        _row(
            event_id="event-reasoning-delta",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id="run-direct",
            event_type="REASONING_DELTA",
            payload={"delta": "hidden reasoning"},
        ),
    )
    unknown = _project_event(
        tmp_path,
        _row(
            event_id="event-unknown-progress",
            event_class=EventClass.PROJECTION_SIGNAL,
            session_id="session-direct",
            run_id="run-direct",
            event_type="FUTURE_PROGRESS",
            payload={"raw": "ignored"},
        ),
    )

    assert content.event_type == "CONTENT_DELTA"
    assert content.activity is None
    assert reasoning.event_type == "REASONING_DELTA"
    assert reasoning.activity is None
    assert unknown.event_class is HostEventClass.PROJECTION_SIGNAL
    assert unknown.event_type == "FUTURE_PROGRESS"
    assert unknown.activity is None


def _project_event(tmp_path: pathlib.Path, row: EventLogRow) -> HostEvent:
    """执行 HostEvent projection。

    :param tmp_path: pytest 临时目录。
    :param row: EventLog row。
    :returns: public HostEvent。
    """

    def _operation(transaction: HostTransaction) -> HostEvent:
        """在 read transaction 内投影事件。

        :param transaction: Host transaction。
        :returns: public HostEvent。
        """

        return _host_event_from_row(transaction, row)

    projected: HostEvent | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        projected = store.transaction_runner.run_read(_operation)
    if projected is None:
        raise AssertionError("HostEvent projection returned no value")
    return projected


def _input_payload_for_run(
    tmp_path: pathlib.Path, run_id: str
) -> Mapping[str, JsonValue]:
    """读取 USER_INPUT_ACCEPTED payload。

    :param tmp_path: pytest 临时目录。
    :param run_id: Run id。
    :returns: payload object。
    :raises HostDurableError: Run 或 input event 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> Mapping[str, JsonValue]:
        """读取 input payload。

        :param transaction: Host transaction。
        :returns: payload object。
        :raises HostDurableError: input event 缺失时抛出。
        """

        run = read_run_by_id(transaction, run_id)
        if run is None:
            raise HostDurableError("run missing")
        row = EventLogStore().read_event_by_id(transaction, run.input_event_id)
        if row is None:
            raise HostDurableError("input event missing")
        return event_payload_object(
            transaction, row, payload_label="USER_INPUT_ACCEPTED"
        )

    payload: Mapping[str, JsonValue] | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        payload = store.transaction_runner.run_read(_operation)
    if payload is None:
        raise AssertionError("USER_INPUT_ACCEPTED payload read returned no value")
    return payload


def _input_event_id_for_run(tmp_path: pathlib.Path, run_id: str) -> str:
    """读取 Run 的 input event id。

    :param tmp_path: pytest 临时目录。
    :param run_id: Run id。
    :returns: input event id。
    :raises HostDurableError: Run 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> str:
        """读取 input event id。

        :param transaction: Host transaction。
        :returns: input event id。
        :raises HostDurableError: Run 缺失时抛出。
        """

        run = read_run_by_id(transaction, run_id)
        if run is None:
            raise HostDurableError("run missing")
        return run.input_event_id

    input_event_id: str | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        input_event_id = store.transaction_runner.run_read(_operation)
    if input_event_id is None:
        raise AssertionError("input event id read returned no value")
    return input_event_id


def _replace_input_payload_for_run(
    tmp_path: pathlib.Path, run_id: str, payload: Mapping[str, JsonValue]
) -> None:
    """替换测试 Run 的 USER_INPUT_ACCEPTED inline payload。

    :param tmp_path: pytest 临时目录。
    :param run_id: Run id。
    :param payload: 新 payload。
    :returns: ``None``。
    """

    input_event_id = _input_event_id_for_run(tmp_path, run_id)

    def _operation(transaction: HostTransaction) -> None:
        """执行 payload 替换。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            UPDATE {TABLE_EVENT_LOG}
            SET payload_json = ?, payload_ref = NULL, payload_digest = NULL
            WHERE event_id = ?
            """,
            (canonical_json_dumps(payload), input_event_id),
        )

    with open_host_durable_store(_durable_options(tmp_path)) as store:
        store.transaction_runner.run_write(_operation)


def _project_tool_call(tmp_path: pathlib.Path, run_id: str) -> HostEvent:
    """投影测试用 TOOL_CALL_REQUESTED event。

    :param tmp_path: pytest 临时目录。
    :param run_id: Run id。
    :returns: public HostEvent。
    """

    return _project_event(
        tmp_path,
        _row(
            event_id=f"event-tool-call-{run_id}",
            event_class=EventClass.PREVIEW,
            session_id="session-direct",
            run_id=run_id,
            event_type="TOOL_CALL_REQUESTED",
            payload={"tool_name": "lookup_filing"},
        ),
    )


def _durable_options(tmp_path: pathlib.Path) -> HostDurableStoreOptions:
    """构造 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: HostDurableStoreOptions。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _row(
    *,
    event_id: str,
    event_class: EventClass,
    session_id: str,
    run_id: str,
    event_type: str,
    payload: Mapping[str, JsonValue],
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogRow:
    """构造测试 EventLog row。

    :param event_id: 事件 id。
    :param event_class: durable event class。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_type: event type。
    :param payload: inline payload。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload descriptor digest。
    :returns: EventLog row。
    """

    return EventLogRow(
        event_sequence=1,
        event_id=event_id,
        event_body_digest="sha256:test",
        event_class=event_class,
        session_id=session_id,
        run_id=run_id,
        attempt_id="attempt-activity",
        execution_id="execution-activity",
        event_type=event_type,
        occurred_at="2026-06-17T08:00:00.000000Z",
        actor="pytest",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json=canonical_json_dumps(payload),
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        appended_at="2026-06-17T08:00:00.000000Z",
    )


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    """

    return EnsureSessionRequest(scope="workspace", slot_key=_SESSION_SLOT, metadata=())


def _followup(
    session_id: str,
    *,
    client_request_id: str,
    tool_names: frozenset[str],
) -> SubmitFollowupRequest:
    """构造 follow-up 请求。

    :param session_id: Session id。
    :param client_request_id: request id。
    :param tool_names: 工具选择集合。
    :returns: SubmitFollowupRequest。
    """

    return SubmitFollowupRequest(
        context=HostCallContext(
            actor="tester",
            source="pytest",
            request_id=client_request_id,
            authorization_claims=(),
            operation_context=OperationContext(
                operation_name="submit_followup",
                operation_kind="interactive",
                business_domain="host",
                business_object_type=None,
                business_object_id=None,
                scenario=None,
                correlation_id=f"trace-{client_request_id}",
            ),
        ),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=None,
        user_prompt="use tools",
        tool_names=tool_names,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _options(
    tmp_path: pathlib.Path, worker_factory: _BlockingWorkerFactory
) -> OpenHostOptions:
    """构造 OpenHostOptions。

    :param tmp_path: pytest 临时目录。
    :param worker_factory: worker factory。
    :returns: OpenHostOptions。
    """

    return OpenHostOptions(
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=3,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.2,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=RunnerSpec(
                provider="test",
                model="test-model",
                endpoint="https://example.invalid",
                api_key_ref="secret:test",
                headers={},
                client_correlation_policy=ClientCorrelationPolicy.DISABLED,
                supports_tool_calling=True,
                supports_streaming=False,
                supports_stream_usage=False,
                default_timeout_seconds=1.0,
                max_retries=0,
                provider_request=None,
            ),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=False,
            ),
            agent_policy=AgentPolicy(
                max_iterations=1,
                continuation_max_attempts=0,
                allow_tool_calls=True,
                tool_execution_timeout_seconds=1.0,
            ),
        ),
        worker_factory=worker_factory,
        tooling_options=HostToolingOptions(
            business_tool_bundle=ToolBundle(
                definitions=(
                    _definition("lookup_filing", display_name="查财报"),
                    _definition("raw_lookup", display_name=None),
                )
            ),
            source_refs=(
                ToolBundleSourceRef(
                    source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                    source_id="activity-test",
                    version_ref=None,
                    content_digest="sha256:"
                    "0123456789abcdef0123456789abcdef"
                    "0123456789abcdef0123456789abcdef",
                ),
            ),
        ),
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
    )


def _definition(name: str, *, display_name: str | None) -> ToolDefinition:
    """构造测试工具定义。

    :param name: 稳定工具名。
    :param display_name: 可选展示名。
    :returns: ToolDefinition。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=f"{name} description",
                parameters=ToolParametersSchema(
                    type="object",
                    properties={},
                    required=(),
                    additional_properties=False,
                ),
            ),
        ),
        callable=_Tool(),
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None if display_name is None else ToolDisplayInfo(name=display_name),
        tags=(),
    )
