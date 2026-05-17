"""Host durable EventLog primitive 测试。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import is_sha256_digest, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
    append_event,
    read_event_by_id,
    read_events_after,
)
from dayu.host.durable.errors import (
    HostDurableError,
    HostEventIdentityConflictError,
    HostForeignKeyError,
    HostPayloadReferenceError,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostTransaction


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.05,
            write_busy_retry_count=2,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.0,
            write_retry_max_delay_seconds=0.001,
        ),
    )


def _request(
    event_id: str,
    *,
    event_class: EventClass = EventClass.CANONICAL_FACT,
    session_id: str = "session-1",
    event_type: str = "host.test",
    payload_json: JsonValue = "payload",
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogAppendRequest:
    """构造标准 EventLog append 请求。

    :param event_id: 事件标识。
    :param event_class: 事件分类。
    :param session_id: session 标识。
    :param event_type: 事件类型。
    :param payload_json: 测试 payload 字符串。
    :param payload_ref: payload descriptor 引用。
    :param payload_digest: payload digest。
    :returns: EventLog append 请求。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=event_class,
        session_id=session_id,
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        event_type=event_type,
        occurred_at=datetime(2026, 5, 14, 1, 2, 3, 123456, tzinfo=UTC),
        actor="host",
        source="test",
        client_request_id="client-1",
        idempotency_key="idem-1",
        policy_decision={"allowed": True},
        reason={"why": "test"},
        payload_json=payload_json,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )


def _count_event_rows(transaction: HostTransaction) -> int:
    """读取 EventLog row count。

    :param transaction: Host transaction。
    :returns: EventLog row count。
    :raises AssertionError: SQLite 未返回 count row 时抛出。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {TABLE_EVENT_LOG}")
    assert row is not None
    total = row.get("total")
    assert isinstance(total, int)
    return total


def test_append_canonical_event_returns_first_sequence(tmp_path: Path) -> None:
    """fresh DB append canonical event 会返回 ``event_sequence=1``。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> int:
            """追加单条 canonical event。

            :param transaction: Host transaction。
            :returns: 写入后的 event_sequence。
            """

            result = append_event(transaction, _request("event-1"))
            assert result.inserted is True
            assert result.row.event_class is EventClass.CANONICAL_FACT
            assert result.row.payload_json == '"payload"'
            assert result.row.policy_decision_json == '{"allowed":true}'
            assert result.row.reason_json == '{"why":"test"}'
            return result.row.event_sequence

        assert store.transaction_runner.run_write(operation) == 1


def test_multiple_event_classes_share_one_global_cursor(tmp_path: Path) -> None:
    """不同 event class 共享同一个全局递增 ``event_sequence``。"""

    classes = (
        EventClass.CANONICAL_FACT,
        EventClass.PREVIEW,
        EventClass.DIAGNOSTIC,
        EventClass.PROJECTION_SIGNAL,
    )
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[int, ...]:
            """追加多类事件。

            :param transaction: Host transaction。
            :returns: 分配到的 event_sequence 元组。
            """

            return tuple(
                append_event(
                    transaction,
                    _request(f"event-{index}", event_class=event_class),
                ).row.event_sequence
                for index, event_class in enumerate(classes)
            )

        assert store.transaction_runner.run_write(operation) == (1, 2, 3, 4)


def test_duplicate_event_id_same_body_returns_existing_row(
    tmp_path: Path,
) -> None:
    """同一 ``event_id`` 和同一事件体返回既有 row 且不增加 row count。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[int, bool, int]:
            """重复追加同体事件。

            :param transaction: Host transaction。
            :returns: 首次序号、第二次 inserted 标记、row count。
            """

            request = _request("event-1")
            first = append_event(transaction, request)
            second = append_event(transaction, request)
            return (
                second.row.event_sequence,
                second.inserted,
                _count_event_rows(transaction),
            )

        assert store.transaction_runner.run_write(operation) == (1, False, 1)


def test_append_optional_none_fields_preserves_nulls_and_digest_idempotency(
    tmp_path: Path,
) -> None:
    """optional 字段为 ``None`` 时 append/read 保留 NULL 且 digest 幂等稳定。"""

    request = EventLogAppendRequest(
        event_id="event-null",
        event_class=EventClass.DIAGNOSTIC,
        session_id="session-null",
        run_id=None,
        attempt_id=None,
        execution_id=None,
        event_type="host.nulls",
        occurred_at=datetime(2026, 5, 14, 1, 2, 3, 123456, tzinfo=UTC),
        actor=None,
        source=None,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"ok": True},
        payload_ref=None,
        payload_digest=None,
    )

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[bool, bool, bool]:
            """追加 optional NULL 事件并验证重复 append 语义。

            :param transaction: Host transaction。
            :returns: 首次插入标记、重复插入标记、NULL 与 digest 校验结果。
            """

            first = append_event(transaction, request)
            second = append_event(transaction, request)
            fetched = read_event_by_id(transaction, request.event_id)
            assert fetched is not None
            none_fields_preserved = (
                fetched.run_id is None
                and fetched.attempt_id is None
                and fetched.execution_id is None
                and fetched.actor is None
                and fetched.source is None
                and fetched.client_request_id is None
                and fetched.idempotency_key is None
                and fetched.policy_decision_json is None
                and fetched.reason_json is None
                and fetched.payload_ref is None
                and fetched.payload_digest is None
            )
            digest_stored_and_stable = (
                is_sha256_digest(first.row.event_body_digest)
                and first.row.event_body_digest == second.row.event_body_digest
                and second.row.event_body_digest == fetched.event_body_digest
            )
            return (
                first.inserted,
                second.inserted,
                none_fields_preserved and digest_stored_and_stable,
            )

        assert store.transaction_runner.run_write(operation) == (True, False, True)


def test_canonical_fact_rejects_oversized_inline_payload_json(
    tmp_path: Path,
) -> None:
    """canonical fact inline payload 超过 payload 阈值时必须要求 ref/digest 边界。"""

    oversized_text = "x" * 70000
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """尝试追加超大 inline canonical fact。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostPayloadReferenceError: inline canonical payload 超限时抛出。
            """

            append_event(
                transaction,
                _request(
                    "event-oversized-inline",
                    payload_json={"content": oversized_text},
                ),
            )

        with pytest.raises(
            HostPayloadReferenceError,
            match="canonical_fact payload_json exceeds inline payload limit",
        ):
            store.transaction_runner.run_write(operation)


def test_duplicate_event_id_different_body_raises_identity_conflict(
    tmp_path: Path,
) -> None:
    """同一 ``event_id`` 但 payload/type/session 不同会抛出 identity conflict。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """触发 EventLog identity conflict。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostEventIdentityConflictError: 重复事件体不一致时抛出。
            """

            append_event(transaction, _request("event-1"))
            append_event(
                transaction,
                _request(
                    "event-1",
                    session_id="session-2",
                    event_type="host.other",
                    payload_json="different",
                ),
            )

        with pytest.raises(HostEventIdentityConflictError):
            store.transaction_runner.run_write(operation)


def test_read_events_after_uses_global_cursor_order(tmp_path: Path) -> None:
    """``read_events_after`` 返回 cursor 之后的全局序号升序 rows。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def write_events(transaction: HostTransaction) -> None:
            """追加三条事件。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(transaction, _request("event-1", session_id="s1"))
            append_event(transaction, _request("event-2", session_id="s2"))
            append_event(transaction, _request("event-3", session_id="s1"))

        def read_events(transaction: HostTransaction) -> tuple[str, ...]:
            """读取 cursor 之后的事件标识。

            :param transaction: Host transaction。
            :returns: event_id 元组。
            """

            rows = read_events_after(transaction, 1, limit=10)
            by_id = read_event_by_id(transaction, "event-2")
            assert by_id is not None
            assert by_id.event_sequence == 2
            return tuple(row.event_id for row in rows)

        store.transaction_runner.run_write(write_events)
        assert store.transaction_runner.run_write(read_events) == ("event-2", "event-3")


def test_event_log_store_wrapper_methods_delegate_to_functions(
    tmp_path: Path,
) -> None:
    """EventLogStore 方法集合会委托 append/read primitive。"""

    event_log_store = EventLogStore()
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[bool, str, tuple[str, ...]]:
            """通过 EventLogStore wrapper 追加并读取事件。

            :param transaction: Host transaction。
            :returns: 插入标记、按 id 读取结果、cursor 读取结果。
            """

            result = event_log_store.append_event(transaction, _request("event-1"))
            fetched = event_log_store.read_event_by_id(transaction, "event-1")
            rows = event_log_store.read_events_after(transaction, 0, limit=10)
            assert fetched is not None
            return (
                result.inserted,
                fetched.event_id,
                tuple(row.event_id for row in rows),
            )

        assert store.transaction_runner.run_write(operation) == (
            True,
            "event-1",
            ("event-1",),
        )


def test_missing_event_and_cursor_beyond_end_return_empty_results(
    tmp_path: Path,
) -> None:
    """缺失 event_id 返回 ``None``，超过末尾 cursor 返回空元组。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[bool, tuple[str, ...]]:
            """验证 EventLog read 边界返回值。

            :param transaction: Host transaction。
            :returns: 缺失 id 判断与超过末尾 cursor 读取结果。
            """

            append_event(transaction, _request("event-1"))
            missing = read_event_by_id(transaction, "missing-event") is None
            beyond_end = read_events_after(transaction, 999, limit=10)
            return missing, tuple(row.event_id for row in beyond_end)

        assert store.transaction_runner.run_write(operation) == (True, ())


def test_invalid_append_inputs_raise_structured_errors(tmp_path: Path) -> None:
    """无效 event class、空文本、naive timestamp 与 payload 引用会结构化失败。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def invalid_event_class(transaction: HostTransaction) -> None:
            """触发 event_class 校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(
                transaction,
                replace(_request("event-1"), event_class=cast(EventClass, "bad")),
            )

        def empty_event_id(transaction: HostTransaction) -> None:
            """触发 event_id 空值校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(transaction, _request(""))

        def whitespace_event_id(transaction: HostTransaction) -> None:
            """触发 event_id 纯空白校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(transaction, _request(" \t"))

        def whitespace_optional_text(transaction: HostTransaction) -> None:
            """触发 optional 文本纯空白校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(transaction, replace(_request("event-space"), run_id=" \n"))

        def whitespace_actor(transaction: HostTransaction) -> None:
            """触发 actor 纯空白校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(
                transaction, replace(_request("event-actor-space"), actor=" \n")
            )

        def whitespace_source(transaction: HostTransaction) -> None:
            """触发 source 纯空白校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(
                transaction, replace(_request("event-source-space"), source=" \t")
            )

        def naive_timestamp(transaction: HostTransaction) -> None:
            """触发 timestamp 格式校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            request = _request("event-2")
            append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=request.event_id,
                    event_class=request.event_class,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    attempt_id=request.attempt_id,
                    execution_id=request.execution_id,
                    event_type=request.event_type,
                    occurred_at=datetime(2026, 5, 14, 1, 2, 3, 123456),
                    actor=request.actor,
                    source=request.source,
                    client_request_id=request.client_request_id,
                    idempotency_key=request.idempotency_key,
                    policy_decision=request.policy_decision,
                    reason=request.reason,
                    payload_json=request.payload_json,
                    payload_ref=request.payload_ref,
                    payload_digest=request.payload_digest,
                ),
            )

        def invalid_payload_ref(transaction: HostTransaction) -> None:
            """触发 payload ref / digest 组合校验失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(
                transaction,
                _request("event-3", payload_ref="payload-1", payload_digest=None),
            )

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(invalid_event_class)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(empty_event_id)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(whitespace_event_id)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(whitespace_optional_text)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(whitespace_actor)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(whitespace_source)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(naive_timestamp)
        with pytest.raises(HostPayloadReferenceError):
            store.transaction_runner.run_write(invalid_payload_ref)


def test_missing_payload_ref_fk_raises_foreign_key_without_retry(
    tmp_path: Path,
) -> None:
    """缺失非空 payload_ref 会抛出 HostForeignKeyError 且不会被 busy retry。"""

    calls: list[str] = []
    digest = sha256_digest_json({"payload": "external"})
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """触发 EventLog payload_ref foreign key 失败。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            calls.append("called")
            append_event(
                transaction,
                _request(
                    "event-1",
                    payload_ref="missing-payload-ref",
                    payload_digest=digest,
                ),
            )

        with pytest.raises(HostForeignKeyError):
            store.transaction_runner.run_write(operation)
        assert calls == ["called"]


def test_after_commit_callback_runs_only_after_append_commit(
    tmp_path: Path,
) -> None:
    """append commit 成功后才执行 after-commit callback。"""

    callback_events: list[str] = []
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> str:
            """追加事件并返回标识。

            :param transaction: Host transaction。
            :returns: 事件标识。
            """

            return append_event(transaction, _request("event-1")).row.event_id

        def after_commit() -> None:
            """记录 after-commit 执行并验证 row 已提交可见。

            :returns: ``None``。
            """

            connection = store.connect()
            try:
                row = connection.execute(
                    f"SELECT COUNT(*) FROM {TABLE_EVENT_LOG}"
                ).fetchone()
                assert row is not None
                callback_events.append(f"count={int(row[0])}")
            finally:
                connection.close()

        assert store.transaction_runner.run_write(
            operation, after_commit=(after_commit,)
        ) == "event-1"
        assert callback_events == ["count=1"]
