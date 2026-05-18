"""Host minimal read model projection 与 repair 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host import (
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    FollowupBehavior,
    HostCallContext,
    HostCommandHandle,
    HostCommandHandleOptions,
    HostInput,
    OperationContext,
    RunStatus,
    StartRunRequest,
    SubmitFollowupRequest,
    cancel_run,
    create_host_command_handle,
    ensure_session,
    start_run,
    submit_followup,
)
from dayu.host.api import EnsureSessionRequest
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.projection import (
    read_projection_checkpoint,
    read_projection_failure,
)
from dayu.host.durable.read_model import (
    RunResultRow,
    SessionTimelineItemRow,
    insert_run_result_if_absent,
    insert_session_timeline_item_if_absent,
    read_run_result,
    read_session_timeline_items,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import (
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.projection import (
    ProjectionConsumerId,
    ProjectionEventView,
    ProjectionRunner,
)
from dayu.host.read_model import (
    MINIMAL_READ_MODEL_CONSUMER_ID,
    MinimalReadModelProjectionConsumer,
    repair_minimal_read_models,
)

_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-projection-read-model",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _context(request_id: str = "trace-read-model") -> HostCallContext:
    """构造测试用 Host call context。

    :param request_id: trace request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="projection_read_model",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase8",
            correlation_id="corr-read-model",
        ),
    )


def _input(display_text: str) -> HostInput:
    """构造 Host 输入。

    :param display_text: 展示文本。
    :returns: Host input。
    """

    return HostInput(
        display_text=display_text,
        payload_ref=None,
        payload_digest=None,
    )


def _start_request(
    session_id: str,
    client_request_id: str,
    *,
    display_text: str = "prompt",
    queue_policy: str = "queue",
) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param display_text: 输入展示文本。
    :param queue_policy: admission queue policy。
    :returns: start run 请求。
    """

    return StartRunRequest(
        context=_context(request_id=f"trace-{client_request_id}"),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(display_text),
        execution_target="projection-target",
        queue_policy=queue_policy,
    )


def _followup_request(
    session_id: str, client_request_id: str, *, display_text: str
) -> SubmitFollowupRequest:
    """构造 submit_followup 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param display_text: 输入展示文本。
    :returns: submit followup 请求。
    """

    return SubmitFollowupRequest(
        context=_context(request_id=f"trace-{client_request_id}"),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(display_text),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _cancel_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: cancel run 请求。
    """

    return CancelRunRequest(
        context=_context(request_id=f"trace-{client_request_id}"),
        client_request_id=client_request_id,
        reason="user_stop",
        mode=CancelMode.GRACEFUL,
    )


def _session_id(host: HostCommandHandle) -> str:
    """创建或读取测试 Session id。

    :param host: Host command handle。
    :returns: Session id。
    """

    return ensure_session(
        host,
        EnsureSessionRequest(scope="workspace", slot_key="slot-read-model", metadata=()),
    ).session_id


def _append_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    session_id: str,
    run_id: str | None,
    event_type: str,
    payload: JsonValue,
) -> EventLogRow:
    """追加测试用 canonical EventLog row。

    :param transaction_runner: Host transaction runner。
    :param event_id: EventLog id。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_type: EventLog type。
    :param payload: inline payload JSON。
    :returns: 已追加 EventLog row。
    """

    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type=event_type,
                occurred_at=datetime(2026, 5, 16, tzinfo=UTC),
                actor="pytest",
                source="projection-read-model",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )


def _run_projection(transaction_runner: HostTransactionRunner, *, limit: int) -> None:
    """运行 minimal read model projection。

    :param transaction_runner: Host transaction runner。
    :param limit: runner scan limit。
    :returns: ``None``。
    """

    ProjectionRunner(
        transaction_runner, (MinimalReadModelProjectionConsumer(),)
    ).run_once(MINIMAL_READ_MODEL_CONSUMER_ID, limit=limit)


def _delete_checkpoint(transaction_runner: HostTransactionRunner) -> None:
    """删除 minimal read model checkpoint，模拟 replay。

    :param transaction_runner: Host transaction runner。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: transaction.execute(
            f"DELETE FROM {TABLE_HOST_PROJECTION_CHECKPOINTS} WHERE consumer_id = ?",
            (MINIMAL_READ_MODEL_CONSUMER_ID.value,),
        )
    )


def _delete_minimal_read_model_owned_rows(
    transaction_runner: HostTransactionRunner,
) -> None:
    """删除 fixed minimal read model consumer 独占的 row。

    :param transaction_runner: Host transaction runner。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: (
            transaction.execute(f"DELETE FROM {TABLE_HOST_SESSION_TIMELINE_ITEMS}"),
            transaction.execute(f"DELETE FROM {TABLE_HOST_RUN_RESULTS}"),
        )
    )


def _read_user_input_texts(
    transaction_runner: HostTransactionRunner, session_id: str
) -> tuple[str | None, ...]:
    """读取 user input timeline 文本。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :returns: user input display_text 元组。
    """

    items = transaction_runner.run_write(
        lambda transaction: read_session_timeline_items(transaction, session_id)
    )
    return tuple(
        item.display_text for item in items if item.item_kind == "user_input"
    )


def _stable_run_result(row: RunResultRow | None) -> tuple[str, ...] | None:
    """返回排除投影时间戳的 RunResult 比较 key。

    :param row: RunResult row 或 ``None``。
    :returns: 稳定比较 key。
    """

    if row is None:
        return None
    return (
        row.run_id,
        row.session_id,
        row.terminal_status,
        row.terminal_event_id,
        str(row.terminal_event_sequence),
        str(row.result_ref),
        str(row.result_digest),
        str(row.summary_ref),
        str(row.summary_digest),
    )


def _stable_timeline(
    rows: tuple[SessionTimelineItemRow, ...]
) -> tuple[tuple[str, ...], ...]:
    """返回排除投影时间戳的 timeline 比较 key。

    :param rows: timeline item rows。
    :returns: 稳定比较 key 元组。
    """

    return tuple(
        (
            row.timeline_item_id,
            row.session_id,
            str(row.run_id),
            row.event_id,
            str(row.event_sequence),
            row.item_kind,
            row.event_type,
            str(row.display_text),
            str(row.payload_ref),
            str(row.payload_digest),
        )
        for row in rows
    )


def _assert_invalid_display_text_fails_without_timeline_item(
    tmp_path: Path, *, event_id: str, display_text: JsonValue
) -> None:
    """断言非法 display_text 只记录 projection failure，不写入 timeline。

    :param tmp_path: pytest 临时目录。
    :param event_id: 待追加的非法 EventLog id。
    :param display_text: 非法 typed display_text 值。
    :returns: ``None``。
    :raises AssertionError: projection failure、checkpoint 或 timeline 断言失败时抛出。
    """

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        transaction_runner = host._transaction_runner()
        invalid_event = _append_event(
            transaction_runner,
            event_id=event_id,
            session_id=session_id,
            run_id=None,
            event_type="USER_INPUT_ACCEPTED",
            payload={"display_text": display_text},
        )
        previous_cursor = invalid_event.event_sequence - 1

        result = ProjectionRunner(
            transaction_runner, (MinimalReadModelProjectionConsumer(),)
        ).run_once(MINIMAL_READ_MODEL_CONSUMER_ID, limit=100)
        checkpoint = transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(
                transaction, MINIMAL_READ_MODEL_CONSUMER_ID.value
            )
        )
        failure = transaction_runner.run_write(
            lambda transaction: read_projection_failure(
                transaction, MINIMAL_READ_MODEL_CONSUMER_ID.value
            )
        )
        items = transaction_runner.run_write(
            lambda transaction: read_session_timeline_items(transaction, session_id)
        )

        assert result.failures == 1
        assert result.finished_cursor == previous_cursor
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == previous_cursor
        assert failure is not None
        assert failure.failed_event_id == invalid_event.event_id
        assert failure.failed_event_sequence == invalid_event.event_sequence
        assert failure.last_error_code == "HostDurableError"
        assert "display_text" in failure.last_error_message
        assert tuple(item for item in items if item.event_id == invalid_event.event_id) == ()
    finally:
        host.close()


def test_terminal_event_projects_run_result_and_duplicate_replay_is_noop(
    tmp_path: Path,
) -> None:
    """terminal fact 生成 RunResult；重复 replay 不插入重复行。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start"))
        transaction_runner = host._transaction_runner()
        terminal = _append_event(
            transaction_runner,
            event_id="event-terminal-success",
            session_id=session_id,
            run_id=run.run_id,
            event_type="RUN_SUCCEEDED",
            payload={
                "terminal_summary_ref": "summary-success",
                "terminal_summary_digest": _DIGEST_A,
            },
        )

        _run_projection(transaction_runner, limit=100)
        _delete_checkpoint(transaction_runner)
        _run_projection(transaction_runner, limit=100)

        result = transaction_runner.run_write(
            lambda transaction: read_run_result(transaction, run.run_id)
        )
        total = transaction_runner.run_write(
            lambda transaction: transaction.fetchone(
                f"SELECT COUNT(*) AS total FROM {TABLE_HOST_RUN_RESULTS}"
            )
        )
        assert result is not None
        assert result.terminal_status == "succeeded"
        assert result.terminal_event_id == terminal.event_id
        assert result.terminal_event_sequence == terminal.event_sequence
        assert result.summary_ref == "summary-success"
        assert result.summary_digest == _DIGEST_A
        assert total is not None
        assert total.get("total") == 1
    finally:
        host.close()


def test_terminal_event_mapping_covers_current_run_terminal_statuses(
    tmp_path: Path,
) -> None:
    """minimal read model terminal event 映射覆盖当前 Run 终态。"""

    terminal_cases = (
        ("RUN_SUCCEEDED", RunStatus.SUCCEEDED),
        ("RUN_FAILED", RunStatus.FAILED),
        ("RUN_CANCELLED", RunStatus.CANCELLED),
        ("RUN_LOST", RunStatus.LOST),
    )
    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        transaction_runner = host._transaction_runner()
        consumer = MinimalReadModelProjectionConsumer()
        run_ids = tuple(
            start_run(
                host,
                _start_request(
                    session_id,
                    f"start-terminal-mapping-{index}",
                    queue_policy="queue",
                ),
            ).run_id
            for index in range(1, len(terminal_cases) + 1)
        )
        terminal_events: list[EventLogRow] = []
        for index, (event_type, status) in enumerate(terminal_cases):
            terminal_events.append(
                _append_event(
                    transaction_runner,
                    event_id=f"event-terminal-{status.value}",
                    session_id=session_id,
                    run_id=run_ids[index],
                    event_type=event_type,
                    payload={},
                )
            )

        for index, event in enumerate(terminal_events):
            transaction_runner.run_write(
                lambda transaction, event=event, index=index: consumer.apply_event(
                        transaction,
                        ProjectionEventView(
                            event_sequence=event.event_sequence,
                            event_id=event.event_id,
                            event_class=event.event_class,
                            event_type=event.event_type,
                            session_id=event.session_id,
                            run_id=run_ids[index],
                            attempt_id=None,
                            execution_id=None,
                            occurred_at=event.occurred_at,
                            payload_ref=None,
                            payload_digest=None,
                            payload={},
                        ),
                    )
            )

        for index, (_event_type, status) in enumerate(terminal_cases):
            result = transaction_runner.run_write(
                lambda transaction, run_id=run_ids[index]: read_run_result(
                    transaction, run_id
                )
            )
            assert result is not None
            assert result.terminal_status == status.value
    finally:
        host.close()


def test_read_model_python_validation_rejects_unknown_terminal_status(
    tmp_path: Path,
) -> None:
    """RunResult Python validation 对未知 terminal_status fail closed。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        transaction_runner = host._transaction_runner()
        row = RunResultRow(
            run_id="run-invalid-status",
            session_id="session-1",
            terminal_status="future_terminal",
            terminal_event_id="event-terminal",
            terminal_event_sequence=1,
            result_ref=None,
            result_digest=None,
            summary_ref=None,
            summary_digest=None,
            projected_at="2026-05-16T00:00:00.000000Z",
            updated_at="2026-05-16T00:00:00.000000Z",
        )

        with pytest.raises(HostDurableError):
            transaction_runner.run_write(
                lambda transaction: insert_run_result_if_absent(transaction, row)
            )
    finally:
        host.close()


def test_read_model_python_validation_rejects_unknown_timeline_kind(
    tmp_path: Path,
) -> None:
    """SessionTimeline Python validation 对未知 item_kind fail closed。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        transaction_runner = host._transaction_runner()
        row = SessionTimelineItemRow(
            timeline_item_id="timeline-invalid-kind",
            session_id="session-1",
            run_id=None,
            event_id="event-1",
            event_sequence=1,
            item_kind="future_kind",
            event_type="USER_INPUT_ACCEPTED",
            display_text=None,
            payload_ref=None,
            payload_digest=None,
            projected_at="2026-05-16T00:00:00.000000Z",
        )

        with pytest.raises(HostDurableError):
            transaction_runner.run_write(
                lambda transaction: insert_session_timeline_item_if_absent(
                    transaction, row
                )
            )
    finally:
        host.close()


def test_conflicting_terminal_event_records_failure_without_overwrite(
    tmp_path: Path,
) -> None:
    """同一 Run 的不同 terminal event 失败，既有 RunResult 不被覆盖。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start"))
        transaction_runner = host._transaction_runner()
        first = _append_event(
            transaction_runner,
            event_id="event-terminal-first",
            session_id=session_id,
            run_id=run.run_id,
            event_type="RUN_FAILED",
            payload={
                "terminal_summary_ref": "summary-first",
                "terminal_summary_digest": _DIGEST_A,
            },
        )
        second = _append_event(
            transaction_runner,
            event_id="event-terminal-conflict",
            session_id=session_id,
            run_id=run.run_id,
            event_type="RUN_LOST",
            payload={
                "terminal_summary_ref": "summary-second",
                "terminal_summary_digest": _DIGEST_B,
            },
        )

        runner = ProjectionRunner(
            transaction_runner, (MinimalReadModelProjectionConsumer(),)
        )
        first_result = runner.run_once(
            MINIMAL_READ_MODEL_CONSUMER_ID, limit=first.event_sequence
        )
        conflict_result = runner.run_once(MINIMAL_READ_MODEL_CONSUMER_ID, limit=100)
        stored = transaction_runner.run_write(
            lambda transaction: read_run_result(transaction, run.run_id)
        )
        checkpoint = transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(
                transaction, MINIMAL_READ_MODEL_CONSUMER_ID.value
            )
        )
        failure = transaction_runner.run_write(
            lambda transaction: read_projection_failure(
                transaction, MINIMAL_READ_MODEL_CONSUMER_ID.value
            )
        )

        assert first_result.failures == 0
        assert conflict_result.failures == 1
        assert stored is not None
        assert stored.terminal_event_id == first.event_id
        assert stored.terminal_event_sequence == first.event_sequence
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == first.event_sequence
        assert failure is not None
        assert failure.failed_event_id == second.event_id
    finally:
        host.close()


def test_user_input_timeline_preserves_repeated_text_and_null_fallback(
    tmp_path: Path,
) -> None:
    """重复输入保留独立 timeline rows；缺少 display_text 时写入 NULL 并保留引用。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        active = start_run(
            host, _start_request(session_id, "start-active", display_text="same")
        )
        queued = submit_followup(
            host,
            session_id,
            _followup_request(session_id, "follow-queued", display_text="same"),
        )
        transaction_runner = host._transaction_runner()
        missing_display = _append_event(
            transaction_runner,
            event_id="event-input-missing-display",
            session_id=session_id,
            run_id=queued.accepted_run_id,
            event_type="USER_INPUT_ACCEPTED",
            payload={
                "payload_ref": "payload-user-input",
                "payload_digest": _DIGEST_A,
            },
        )

        _run_projection(transaction_runner, limit=100)

        items = transaction_runner.run_write(
            lambda transaction: read_session_timeline_items(transaction, session_id)
        )
        user_inputs = tuple(item for item in items if item.item_kind == "user_input")
        null_item = next(
            item for item in user_inputs if item.event_id == missing_display.event_id
        )
        assert active.run_id != queued.accepted_run_id
        assert _read_user_input_texts(transaction_runner, session_id).count("same") == 2
        assert len({item.timeline_item_id for item in user_inputs}) == len(user_inputs)
        assert null_item.display_text is None
        assert null_item.payload_ref == "payload-user-input"
        assert null_item.payload_digest == _DIGEST_A
    finally:
        host.close()


def test_numeric_user_input_display_text_records_projection_failure(
    tmp_path: Path,
) -> None:
    """数字 display_text 触发 projection failure。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: projection failure、checkpoint 或 timeline 断言失败时抛出。
    """

    _assert_invalid_display_text_fails_without_timeline_item(
        tmp_path,
        event_id="event-input-numeric-display",
        display_text=123,
    )


def test_empty_user_input_display_text_records_projection_failure(
    tmp_path: Path,
) -> None:
    """空字符串 display_text 触发 projection failure。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: projection failure、checkpoint 或 timeline 断言失败时抛出。
    """

    _assert_invalid_display_text_fails_without_timeline_item(
        tmp_path,
        event_id="event-input-empty-display",
        display_text="",
    )


def test_cancelled_input_and_later_input_remain_separate_items(
    tmp_path: Path,
) -> None:
    """取消 Run 的输入与后续新输入保持两条独立 timeline rows。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        start_run(host, _start_request(session_id, "start-active"))
        cancelled = start_run(
            host,
            _start_request(
                session_id,
                "start-cancelled",
                display_text="cancelled input",
                queue_policy="queue",
            ),
        )
        cancel_run(host, cancelled.run_id, _cancel_request("cancel-queued"))
        later = submit_followup(
            host,
            session_id,
            _followup_request(session_id, "later-input", display_text="later input"),
        )
        transaction_runner = host._transaction_runner()

        _run_projection(transaction_runner, limit=100)

        texts = _read_user_input_texts(transaction_runner, session_id)
        assert cancelled.run_id != later.accepted_run_id
        assert "cancelled input" in texts
        assert "later input" in texts
    finally:
        host.close()


def test_repair_rebuilds_rows_after_deletion_and_reset(tmp_path: Path) -> None:
    """repair reset 删除读模型与 checkpoint 后可从 EventLog 重建同等 rows。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start"))
        transaction_runner = host._transaction_runner()
        _append_event(
            transaction_runner,
            event_id="event-terminal-repair",
            session_id=session_id,
            run_id=run.run_id,
            event_type="RUN_SUCCEEDED",
            payload={
                "terminal_summary_ref": "summary-repair",
                "terminal_summary_digest": _DIGEST_A,
            },
        )
        repair_minimal_read_models(
            transaction_runner, reset_checkpoint=True, batch_size=2
        )
        before_result = transaction_runner.run_write(
            lambda transaction: read_run_result(transaction, run.run_id)
        )
        before_timeline = transaction_runner.run_write(
            lambda transaction: read_session_timeline_items(transaction, session_id)
        )

        transaction_runner.run_write(
            lambda transaction: (
                transaction.execute(f"DELETE FROM {TABLE_HOST_SESSION_TIMELINE_ITEMS}"),
                transaction.execute(f"DELETE FROM {TABLE_HOST_RUN_RESULTS}"),
                transaction.execute(
                    f"""
                    DELETE FROM {TABLE_HOST_PROJECTION_CHECKPOINTS}
                    WHERE consumer_id = ?
                    """,
                    (MINIMAL_READ_MODEL_CONSUMER_ID.value,),
                ),
            )
        )
        repair = repair_minimal_read_models(
            transaction_runner, reset_checkpoint=False, batch_size=2
        )
        after_result = transaction_runner.run_write(
            lambda transaction: read_run_result(transaction, run.run_id)
        )
        after_timeline = transaction_runner.run_write(
            lambda transaction: read_session_timeline_items(transaction, session_id)
        )

        assert repair.failures == 0
        assert _stable_run_result(before_result) == _stable_run_result(after_result)
        assert _stable_timeline(before_timeline) == _stable_timeline(after_timeline)
    finally:
        host.close()


def test_minimal_read_model_reset_replays_fixed_consumer_owned_tables(
    tmp_path: Path,
) -> None:
    """fixed minimal consumer 可清空独占 read model tables 并从 EventLog 重建。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start-reset-replay"))
        transaction_runner = host._transaction_runner()
        _append_event(
            transaction_runner,
            event_id="event-terminal-reset-replay",
            session_id=session_id,
            run_id=run.run_id,
            event_type="RUN_SUCCEEDED",
            payload={
                "terminal_summary_ref": "summary-reset-replay",
                "terminal_summary_digest": _DIGEST_A,
            },
        )
        repair_minimal_read_models(
            transaction_runner, reset_checkpoint=True, batch_size=2
        )
        before_result = transaction_runner.run_write(
            lambda transaction: read_run_result(transaction, run.run_id)
        )
        before_timeline = transaction_runner.run_write(
            lambda transaction: read_session_timeline_items(transaction, session_id)
        )

        _delete_minimal_read_model_owned_rows(transaction_runner)
        repair = repair_minimal_read_models(
            transaction_runner, reset_checkpoint=True, batch_size=2
        )
        after_result = transaction_runner.run_write(
            lambda transaction: read_run_result(transaction, run.run_id)
        )
        after_timeline = transaction_runner.run_write(
            lambda transaction: read_session_timeline_items(transaction, session_id)
        )

        assert repair.consumer_id == MINIMAL_READ_MODEL_CONSUMER_ID
        assert repair.started_cursor == 0
        assert repair.failures == 0
        assert _stable_run_result(before_result) == _stable_run_result(after_result)
        assert _stable_timeline(before_timeline) == _stable_timeline(after_timeline)
    finally:
        host.close()


def test_repair_failure_resumes_from_last_committed_checkpoint(
    tmp_path: Path,
) -> None:
    """repair 后续 batch 失败时保留 checkpoint，下一次从该 cursor 继续。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        session_id = _session_id(host)
        run = start_run(host, _start_request(session_id, "start"))
        transaction_runner = host._transaction_runner()
        first = _append_event(
            transaction_runner,
            event_id="event-terminal-before-conflict",
            session_id=session_id,
            run_id=run.run_id,
            event_type="RUN_FAILED",
            payload={
                "terminal_summary_ref": "summary-before-conflict",
                "terminal_summary_digest": _DIGEST_A,
            },
        )
        _append_event(
            transaction_runner,
            event_id="event-terminal-repair-conflict",
            session_id=session_id,
            run_id=run.run_id,
            event_type="RUN_LOST",
            payload={
                "terminal_summary_ref": "summary-conflict",
                "terminal_summary_digest": _DIGEST_B,
            },
        )

        first_repair = repair_minimal_read_models(
            transaction_runner, reset_checkpoint=True, batch_size=1
        )
        second_repair = repair_minimal_read_models(
            transaction_runner, reset_checkpoint=False, batch_size=1
        )
        checkpoint = transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(
                transaction, MINIMAL_READ_MODEL_CONSUMER_ID.value
            )
        )

        assert first_repair.failures == 1
        assert first_repair.finished_cursor == first.event_sequence
        assert second_repair.started_cursor == first.event_sequence
        assert second_repair.failures == 1
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == first.event_sequence
    finally:
        host.close()


def test_repair_result_uses_minimal_consumer_id(tmp_path: Path) -> None:
    """repair result 返回强类型 minimal consumer id。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        result = repair_minimal_read_models(
            host._transaction_runner(), reset_checkpoint=True, batch_size=1
        )
        assert result.consumer_id == ProjectionConsumerId("host.minimal-read-model")
    finally:
        host.close()
