"""Host Phase 5 RunInputBuilder 与 no-tool provider 测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    SystemMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    EnsureSessionRequest,
    HostCallContext,
    HostMetadataEntry,
    OperationContext,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    CreateRunningRunInput,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import RunStartReason, WorkerKind
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.run_input import (
    NoToolExecutor,
    PolicySnapshot,
    create_no_tool_run_input_builder,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "run-input-test"})
_INPUT_DIGEST = sha256_digest_json({"input": "current"})
_POLICY_REF = "policy-snapshot-p5-s2"


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的当前 running Run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _NeverCancelledToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


def test_current_user_message_comes_from_durable_user_input(
    tmp_path: Path,
) -> None:
    """当前用户消息只来自 durable USER_INPUT_ACCEPTED canonical fact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        payload: dict[str, JsonValue] = _user_input_payload("durable prompt")
        seeded = _seed_current_run(store, session_id=session_id, payload=payload)
        payload["display_text"] = "mutated transient prompt"

        request = _build_request(store, seeded)

        assert isinstance(request.messages[-1], UserMessage)
        assert request.messages[-1].content == "durable prompt"


def test_build_is_deterministic_for_same_eventlog_and_policy(
    tmp_path: Path,
) -> None:
    """同一 EventLog 与 policy snapshot 多次 build 输出稳定 messages。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior",
            user_text="earlier question",
            answer_text="earlier answer",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        first = _build_request(store, seeded)
        second = _build_request(store, seeded)

        assert tuple(_message_content(message) for message in first.messages) == tuple(
            _message_content(message) for message in second.messages
        )


def test_continuity_uses_event_sequence_and_ignores_non_canonical(
    tmp_path: Path,
) -> None:
    """continuity provider 按 event_sequence 排序且不消费非 canonical 事件。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-1",
            event_id="event-prior-user-1",
            text="first question",
        )
        _append_projection_signal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-ignored",
        )
        _append_prior_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-1",
            event_id="event-prior-success-1",
            answer_text="first answer",
        )
        _append_preview_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-preview",
        )
        _append_prior_user(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-prior-2",
            event_id="event-prior-user-2",
            text="second question",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        request = _build_request(store, seeded)
        contents = tuple(_message_content(message) for message in request.messages)

        assert contents == (
            _expected_system_content(),
            "first question",
            "first answer",
            "current question",
        )


def test_continuity_skips_unsuccessful_prior_runs(tmp_path: Path) -> None:
    """failed/cancelled/lost 历史 Run 不留下孤立 user message。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_prior_user_and_terminal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-failed",
            user_text="failed question",
            terminal_event_type="RUN_FAILED",
        )
        _append_prior_user_and_terminal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-cancelled",
            user_text="cancelled question",
            terminal_event_type="RUN_CANCELLED",
        )
        _append_prior_user_and_terminal(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-lost",
            user_text="lost question",
            terminal_event_type="RUN_LOST",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        request = _build_request(store, seeded)
        contents = tuple(_message_content(message) for message in request.messages)

        assert contents == (_expected_system_content(), "current question")


def test_noop_providers_do_not_create_durable_rows(tmp_path: Path) -> None:
    """noop memory / compact / tool schema provider 不创建 durable rows。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )
        before = _table_counts(store.transaction_runner)

        _build_request(store, seeded)

        assert _table_counts(store.transaction_runner) == before


def test_no_tool_request_fields_are_disabled(tmp_path: Path) -> None:
    """RunInputBuilder 输出 no-tool AgentRunRequest。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            payload=_user_input_payload("current question"),
        )

        request = _build_request(store, seeded)

        assert request.disable_tools is True
        assert request.tool_schemas == ()
        assert request.agent_policy.allow_tool_calls is False
        assert isinstance(request.tool_executor, NoToolExecutor)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

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


def _context() -> HostCallContext:
    """构造标准 Host call context。

    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="request-trace",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="run_input_builder_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase5",
            correlation_id="corr-run-input",
        ),
    )


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """创建测试 Session 并返回 id。

    :param transaction_runner: Host transaction runner。
    :returns: Session id。
    """

    result = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key="run-input",
            metadata=(HostMetadataEntry(key="case", value="run-input"),),
        ),
    )
    return result.snapshot.session_id


def _seed_current_run(
    store: HostDurableStore,
    *,
    session_id: str,
    payload: JsonValue,
) -> _SeededRun:
    """写入当前 running Run / STARTING Attempt / pending dispatch。

    :param store: Host durable store。
    :param session_id: Session id。
    :param payload: 当前 USER_INPUT_ACCEPTED payload。
    :returns: seeded Run 引用。
    """

    def operation(transaction: HostTransaction) -> _SeededRun:
        """执行当前 Run 写入。

        :param transaction: Host transaction。
        :returns: seeded Run 引用。
        """

        input_event = _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id="run-current",
            event_id="event-current-input",
            payload=payload,
            event_class=EventClass.CANONICAL_FACT,
        )
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id="run-current",
                client_request_id="request-current",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-current",
                run_started_event_id="event-run-started-current",
                attempt_started_event_id="event-attempt-started-current",
                attempt_id="attempt-current",
                execution_id="execution-current",
                dispatch_record_id="dispatch-current",
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                idempotency_key="request-current",
                execution_target="local-default",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        return _SeededRun(
            session_id=session_id,
            run_id="run-current",
            attempt_id="attempt-current",
            execution_id="execution-current",
            dispatch_record_id="dispatch-current",
        )

    return store.transaction_runner.run_write(operation)


def _build_request(
    store: HostDurableStore, seeded: _SeededRun
) -> AgentRunRequest:
    """通过默认 no-tool RunInputBuilder 构造 AgentRunRequest。

    :param store: Host durable store。
    :param seeded: seeded Run 引用。
    :returns: AgentRunRequest。
    """

    builder = create_no_tool_run_input_builder(
        transaction_runner=store.transaction_runner,
        policy_snapshot=_policy_snapshot(),
    )
    return builder.build(
        AttemptDispatchSnapshot(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=seeded.execution_id,
            dispatch_record_id=seeded.dispatch_record_id,
            execution_target="local-default",
            policy_snapshot_ref=_POLICY_REF,
            cancellation_token=_token(),
        )
    )


def _token() -> CancellationToken:
    """构造测试用 cancellation token。

    :returns: 未取消 token。
    """

    return _NeverCancelledToken()


def _policy_snapshot() -> PolicySnapshot:
    """构造测试用 no-tool policy snapshot。

    :returns: PolicySnapshot。
    """

    return PolicySnapshot(
        runner_spec=RunnerSpec(
            provider="test",
            model="test-model",
            endpoint="https://example.invalid/v1",
            api_key_ref="test-key",
            headers={},
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            default_timeout_seconds=30.0,
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
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
        ),
        policy_snapshot_ref=_POLICY_REF,
    )


def _append_prior_user_and_success(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    user_text: str,
    answer_text: str,
) -> None:
    """追加一组历史 user / assistant continuity facts。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: 历史 Run id。
    :param user_text: user message 文本。
    :param answer_text: assistant answer 文本。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加历史 facts。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=f"event-{run_id}-input",
            payload=_user_input_payload(user_text),
            event_class=EventClass.CANONICAL_FACT,
        )
        _append_success_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=f"event-{run_id}-success",
            answer_text=answer_text,
            event_class=EventClass.CANONICAL_FACT,
        )

    transaction_runner.run_write(operation)


def _append_prior_user(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    text: str,
) -> None:
    """追加历史 USER_INPUT_ACCEPTED canonical fact。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param text: user 文本。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=event_id,
            payload=_user_input_payload(text),
            event_class=EventClass.CANONICAL_FACT,
        )
    )


def _append_prior_user_and_terminal(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    user_text: str,
    terminal_event_type: str,
) -> None:
    """追加一个非成功历史 Run 的 user 与 terminal fact。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param user_text: user 文本。
    :param terminal_event_type: terminal event type。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加测试 facts。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=f"event-{run_id}-input",
            payload=_user_input_payload(user_text),
            event_class=EventClass.CANONICAL_FACT,
        )
        EventLogStore().append_event(
            transaction,
            _event_request(
                event_id=f"event-{run_id}-terminal",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                event_type=terminal_event_type,
                payload={"reason": terminal_event_type.lower()},
            ),
        )

    transaction_runner.run_write(operation)


def _append_prior_success(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    answer_text: str,
) -> None:
    """追加历史 RUN_SUCCEEDED canonical fact。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param answer_text: assistant answer 文本。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: _append_success_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=event_id,
            answer_text=answer_text,
            event_class=EventClass.CANONICAL_FACT,
        )
    )


def _append_projection_signal(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
) -> None:
    """追加应被 RunInputBuilder 忽略的 projection_signal 事件。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: EventLogStore().append_event(
            transaction,
            _event_request(
                event_id="event-projection-signal",
                event_class=EventClass.PROJECTION_SIGNAL,
                session_id=session_id,
                run_id=run_id,
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "ignored projection"},
            ),
        )
    )


def _append_preview_user_input(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
) -> None:
    """追加应被 RunInputBuilder 忽略的 preview user input 事件。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: _append_user_input_tx(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id="event-preview-user",
            payload=_user_input_payload("ignored preview"),
            event_class=EventClass.PREVIEW,
        )
    )


def _append_user_input_tx(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    payload: JsonValue,
    event_class: EventClass,
) -> EventLogRow:
    """在 transaction 内追加 USER_INPUT_ACCEPTED event。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param payload: event payload。
    :param event_class: event class。
    :returns: EventLog row。
    """

    return EventLogStore().append_event(
        transaction,
        _event_request(
            event_id=event_id,
            event_class=event_class,
            session_id=session_id,
            run_id=run_id,
            event_type="USER_INPUT_ACCEPTED",
            payload=payload,
        ),
    ).row


def _append_success_tx(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    answer_text: str,
    event_class: EventClass,
) -> EventLogRow:
    """在 transaction 内追加 RUN_SUCCEEDED event。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param answer_text: assistant answer 文本。
    :param event_class: event class。
    :returns: EventLog row。
    """

    return EventLogStore().append_event(
        transaction,
        _event_request(
            event_id=event_id,
            event_class=event_class,
            session_id=session_id,
            run_id=run_id,
            event_type="RUN_SUCCEEDED",
            payload={"final_answer": answer_text},
        ),
    ).row


def _event_request(
    *,
    event_id: str,
    event_class: EventClass,
    session_id: str,
    run_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogAppendRequest:
    """构造测试用 EventLog append request。

    :param event_id: event id。
    :param event_class: event class。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_type: event type。
    :param payload: payload。
    :returns: EventLogAppendRequest。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=event_class,
        session_id=session_id,
        run_id=run_id,
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _user_input_payload(text: str) -> dict[str, JsonValue]:
    """构造 USER_INPUT_ACCEPTED payload。

    :param text: display text。
    :returns: payload dict。
    """

    return {
        "input_ref": None,
        "input_digest": _INPUT_DIGEST,
        "display_text": text,
        "payload_ref": None,
        "payload_digest": None,
        "operation_kind": "start_run",
        "call_context_digest": _CALL_CONTEXT_DIGEST,
    }


def _message_content(message: AgentMessage) -> str:
    """读取测试关心的 message 内容。

    :param message: Engine message。
    :returns: message content。
    :raises AssertionError: assistant content 缺失时抛出。
    """

    if isinstance(message, AssistantMessage):
        assert message.content is not None
        return message.content
    if isinstance(message, SystemMessage | UserMessage):
        return message.content
    raise AssertionError("tool messages are not expected in RunInputBuilder tests")


def _expected_system_content() -> str:
    """构造期望 system message 内容。

    :returns: system message content。
    """

    return "\n".join(
        (
            "Host execution context:",
            "operation_kind=start_run",
            "execution_target=local-default",
            "queue_policy=queue",
            f"policy_snapshot_ref={_POLICY_REF}",
            "tools=disabled",
        )
    )


def _table_counts(
    transaction_runner: HostTransactionRunner,
) -> tuple[int, int, int]:
    """统计 RunInputBuilder 不应写入的 durable table 数量。

    :param transaction_runner: Host transaction runner。
    :returns: event_log、payload_descriptors、sqlite_payloads row 数。
    """

    def operation(transaction: HostTransaction) -> tuple[int, int, int]:
        """读取 table counts。

        :param transaction: Host transaction。
        :returns: 三个 table row 数。
        """

        return (
            _count_table(transaction, "event_log"),
            _count_table(transaction, "payload_descriptors"),
            _count_table(transaction, "host_sqlite_payloads"),
        )

    return transaction_runner.run_read(operation)


def _count_table(transaction: HostTransaction, table_name: str) -> int:
    """统计指定 table 的 row 数。

    :param transaction: Host transaction。
    :param table_name: table name。
    :returns: row 数。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
    assert row is not None
    return _required_int(row, "total")


def _required_int(row: HostRow, column: str) -> int:
    """从 HostRow 读取整数。

    :param row: Host row。
    :param column: column name。
    :returns: int 值。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value
