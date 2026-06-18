"""Host ProjectionRunner typed consumer 与 checkpoint 行为测试。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.projection import (
    read_projection_checkpoint,
    read_projection_failure,
    write_projection_failure,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.projection import (
    ProjectionApplyResult,
    ProjectionApplyStatus,
    ProjectionConsumerId,
    ProjectionEventClassFilter,
    ProjectionEventFilter,
    ProjectionEventView,
    ProjectionRunner,
)


class _ConsumerFailure(RuntimeError):
    """测试 consumer 主动失败异常。"""


@dataclass(slots=True)
class _FakeConsumer:
    """测试用 projection consumer。

    :param consumer_id_value: consumer id 文本。
    :param event_filter_value: EventLog filter。
    :param write_seen_rows: 是否向测试 projection table 写入 seen row。
    :param fail_event_ids: 需要主动失败的 EventLog id 集合。
    :param duplicate_event_ids: 需要返回 duplicate 的 EventLog id 集合。
    """

    consumer_id_value: str
    event_filter_value: ProjectionEventFilter
    write_seen_rows: bool = False
    fail_event_ids: frozenset[str] = frozenset()
    duplicate_event_ids: frozenset[str] = frozenset()
    applied_events: list[ProjectionEventView] = field(default_factory=list)

    @property
    def consumer_id(self) -> ProjectionConsumerId:
        """返回测试 consumer id。

        :returns: projection consumer id。
        """

        return ProjectionConsumerId(self.consumer_id_value)

    @property
    def event_filter(self) -> ProjectionEventFilter:
        """返回测试 event filter。

        :returns: projection event filter。
        """

        return self.event_filter_value

    def apply_event(
        self, transaction: HostTransaction, event: ProjectionEventView
    ) -> ProjectionApplyResult:
        """记录或写入测试 projection row。

        :param transaction: 当前 Host durable transaction。
        :param event: typed projection event view。
        :returns: projection apply result。
        :raises _ConsumerFailure: event id 命中失败集合时抛出。
        """

        self.applied_events.append(event)
        if self.write_seen_rows:
            transaction.execute(
                """
                INSERT INTO projection_seen_events (
                  consumer_id,
                  event_id,
                  event_sequence,
                  marker
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    self.consumer_id_value,
                    event.event_id,
                    event.event_sequence,
                    _payload_marker(event),
                ),
            )
        if event.event_id in self.fail_event_ids:
            raise _ConsumerFailure("consumer failed")
        if event.event_id in self.duplicate_event_ids:
            return ProjectionApplyResult(ProjectionApplyStatus.DUPLICATE)
        return ProjectionApplyResult(ProjectionApplyStatus.APPLIED)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )


def _append_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    event_class: EventClass,
    event_type: str,
    marker: str,
) -> EventLogRow:
    """追加一条测试 EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_class: EventLog class。
    :param event_type: EventLog type。
    :param marker: 写入 payload 的标记文本。
    :returns: 已追加的 EventLog row。
    """

    payload: JsonValue = {"marker": marker}
    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=event_class,
                session_id="session-1",
                run_id="run-1",
                attempt_id=None,
                execution_id=None,
                event_type=event_type,
                occurred_at=datetime(2026, 5, 16, tzinfo=UTC),
                actor=None,
                source=None,
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


def _replace_event_payload_json(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    payload_json: str,
) -> None:
    """直接替换测试 EventLog row 的 payload_json。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param payload_json: 写入 EventLog row 的 payload_json 文本。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: transaction.execute(
            f"""
            UPDATE {TABLE_EVENT_LOG}
            SET payload_json = ?
            WHERE event_id = ?
            """,
            (payload_json, event_id),
        )
    )


def _create_seen_table(transaction_runner: HostTransactionRunner) -> None:
    """创建测试 projection-owned table。

    :param transaction_runner: Host durable transaction runner。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: transaction.execute(
            """
            CREATE TABLE projection_seen_events (
              consumer_id TEXT NOT NULL,
              event_id TEXT PRIMARY KEY,
              event_sequence INTEGER NOT NULL,
              marker TEXT NOT NULL
            )
            """
        )
    )


def _seen_rows(
    transaction_runner: HostTransactionRunner,
) -> tuple[tuple[str, str, int, str], ...]:
    """读取测试 projection table rows。

    :param transaction_runner: Host durable transaction runner。
    :returns: seen rows 元组。
    """

    rows = transaction_runner.run_write(
        lambda transaction: transaction.fetchall(
            """
            SELECT consumer_id, event_id, event_sequence, marker
            FROM projection_seen_events
            ORDER BY event_sequence ASC
            """
        )
    )
    return tuple(
        (
            str(row.get("consumer_id")),
            str(row.get("event_id")),
            _row_int(row.get("event_sequence")),
            str(row.get("marker")),
        )
        for row in rows
    )


def _row_int(value: None | int | float | str | bytes) -> int:
    """把 SQLite scalar 收窄为测试所需整数。

    :param value: SQLite scalar 值。
    :returns: 整数值。
    :raises AssertionError: 值不是整数时抛出。
    """

    assert isinstance(value, int)
    return value


def _payload_marker(event: ProjectionEventView) -> str:
    """从 typed projection payload 中读取测试 marker。

    :param event: typed projection event view。
    :returns: marker 文本。
    :raises AssertionError: marker 缺失或类型错误时抛出。
    """

    marker = event.payload.get("marker")
    assert isinstance(marker, str)
    return marker


def _canonical_type_filter(*event_types: str) -> ProjectionEventFilter:
    """构造 canonical fact 类型过滤器。

    :param event_types: event type 白名单。
    :returns: projection event filter。
    """

    return ProjectionEventFilter(
        (
            ProjectionEventClassFilter(
                EventClass.CANONICAL_FACT,
                event_types,
            ),
        )
    )


def test_runner_filters_matching_events_in_sequence_order(
    tmp_path: Path,
) -> None:
    """runner 只调用匹配事件，并按 event_sequence 升序处理。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="one",
        )
        _append_event(
            store.transaction_runner,
            event_id="event-2",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_B",
            marker="two",
        )
        _append_event(
            store.transaction_runner,
            event_id="event-3",
            event_class=EventClass.DIAGNOSTIC,
            event_type="DIAG_A",
            marker="three",
        )
        consumer = _FakeConsumer(
            "consumer",
            ProjectionEventFilter(
                (
                    ProjectionEventClassFilter(
                        EventClass.CANONICAL_FACT, ("TYPE_A",)
                    ),
                    ProjectionEventClassFilter(EventClass.DIAGNOSTIC, None),
                )
            ),
        )
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=10
        )
        assert [event.event_id for event in consumer.applied_events] == [
            "event-1",
            "event-3",
        ]
        assert result.events_scanned == 2
        assert result.events_matched == 2
        assert result.events_applied == 2
        assert result.finished_cursor == 3
        assert [_payload_marker(event) for event in consumer.applied_events] == [
            "one",
            "three",
        ]


def test_per_class_filters_do_not_share_event_type_sets(
    tmp_path: Path,
) -> None:
    """每个 EventClass 独立使用自己的 event_types 过滤规则。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_B",
            marker="canonical",
        )
        _append_event(
            store.transaction_runner,
            event_id="event-2",
            event_class=EventClass.DIAGNOSTIC,
            event_type="DIAG_B",
            marker="diagnostic-b",
        )
        _append_event(
            store.transaction_runner,
            event_id="event-3",
            event_class=EventClass.DIAGNOSTIC,
            event_type="DIAG_A",
            marker="diagnostic-a",
        )
        consumer = _FakeConsumer(
            "consumer",
            ProjectionEventFilter(
                (
                    ProjectionEventClassFilter(EventClass.CANONICAL_FACT, None),
                    ProjectionEventClassFilter(EventClass.DIAGNOSTIC, ("DIAG_A",)),
                )
            ),
        )
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=10
        )
        assert [event.event_id for event in consumer.applied_events] == [
            "event-1",
            "event-3",
        ]


def test_runner_commits_projection_write_and_checkpoint_together(
    tmp_path: Path,
) -> None:
    """consumer projection write 与 checkpoint advance 在同一 runner transaction 提交。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _create_seen_table(store.transaction_runner)
        event = _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="one",
        )
        consumer = _FakeConsumer(
            "consumer",
            _canonical_type_filter("TYPE_A"),
            write_seen_rows=True,
        )
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=1
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        seen_rows = _seen_rows(store.transaction_runner)
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == event.event_sequence
        assert seen_rows == (("consumer", "event-1", event.event_sequence, "one"),)


def test_consumer_write_failure_rolls_back_write_and_checkpoint(
    tmp_path: Path,
) -> None:
    """consumer 失败时 projection write rollback，checkpoint 不推进，只记录 failure。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _create_seen_table(store.transaction_runner)
        event = _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="one",
        )
        consumer = _FakeConsumer(
            "consumer",
            _canonical_type_filter("TYPE_A"),
            write_seen_rows=True,
            fail_event_ids=frozenset({"event-1"}),
        )
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=1
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        failure = store.transaction_runner.run_write(
            lambda transaction: read_projection_failure(transaction, "consumer")
        )
        seen_rows = _seen_rows(store.transaction_runner)
        assert result.failures == 1
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 0
        assert failure is not None
        assert failure.failed_event_sequence == event.event_sequence
        assert failure.failed_event_id == event.event_id
        assert seen_rows == ()


@pytest.mark.parametrize(
    ("payload_json", "expected_error_message"),
    (
        ("[]", "EventLog payload_json must be a JSON mapping"),
        ("{", "EventLog payload_json is invalid"),
    ),
)
def test_payload_parsing_failure_records_failure_without_advancing_checkpoint(
    tmp_path: Path,
    payload_json: str,
    expected_error_message: str,
) -> None:
    """payload 无法构造 typed view 时记录 failure，且不推进 checkpoint。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="one",
        )
        _replace_event_payload_json(
            store.transaction_runner,
            event_id=event.event_id,
            payload_json=payload_json,
        )
        consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=1
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        failure = store.transaction_runner.run_write(
            lambda transaction: read_projection_failure(transaction, "consumer")
        )
        assert result.failures == 1
        assert result.finished_cursor == 0
        assert result.events_scanned == 0
        assert consumer.applied_events == []
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 0
        assert failure is not None
        assert failure.failed_event_sequence == event.event_sequence
        assert failure.failed_event_id == event.event_id
        assert failure.last_error_code == "HostDurableError"
        assert failure.last_error_message == expected_error_message


def test_duplicate_apply_result_still_advances_checkpoint(
    tmp_path: Path,
) -> None:
    """consumer 返回 duplicate 时 runner 仍推进 checkpoint。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="one",
        )
        consumer = _FakeConsumer(
            "consumer",
            _canonical_type_filter("TYPE_A"),
            duplicate_event_ids=frozenset({"event-1"}),
        )
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=1
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        assert result.duplicate_events == 1
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == event.event_sequence


def test_success_after_failure_clears_failure_row(tmp_path: Path) -> None:
    """同一 cursor 后续成功处理会清除既有 failure row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="one",
        )
        failing_consumer = _FakeConsumer(
            "consumer",
            _canonical_type_filter("TYPE_A"),
            fail_event_ids=frozenset({"event-1"}),
        )
        ProjectionRunner(store.transaction_runner, (failing_consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=1
        )
        successful_consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        ProjectionRunner(store.transaction_runner, (successful_consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=1
        )
        failure = store.transaction_runner.run_write(
            lambda transaction: read_projection_failure(transaction, "consumer")
        )
        assert failure is None


def test_runner_skips_unmatched_events_and_advances_to_matching_checkpoint(
    tmp_path: Path,
) -> None:
    """runner 通过 durable filter 跳过不匹配事件，并推进到匹配 row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_B",
            marker="unmatched-canonical",
        )
        _append_event(
            store.transaction_runner,
            event_id="event-2",
            event_class=EventClass.DIAGNOSTIC,
            event_type="DIAG_A",
            marker="unmatched-diagnostic",
        )
        matched = _append_event(
            store.transaction_runner,
            event_id="event-3",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="matched",
        )
        consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=1
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        assert [event.event_id for event in consumer.applied_events] == ["event-3"]
        assert result.events_scanned == 1
        assert result.events_matched == 1
        assert result.finished_cursor == matched.event_sequence
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == matched.event_sequence


def test_runner_advances_covered_cursor_without_apply_when_no_matching_rows(
    tmp_path: Path,
) -> None:
    """没有匹配 row 但存在 covered row 时 runner 只推进 checkpoint。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_B",
            marker="one",
        )
        latest = _append_event(
            store.transaction_runner,
            event_id="event-2",
            event_class=EventClass.DIAGNOSTIC,
            event_type="DIAG_A",
            marker="two",
        )
        consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=10
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        assert consumer.applied_events == []
        assert result.events_scanned == 1
        assert result.events_matched == 0
        assert result.finished_cursor == latest.event_sequence
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == latest.event_sequence
        assert checkpoint.checkpoint_event_id == latest.event_id


def test_runner_clears_failure_when_covered_cursor_advances_without_match(
    tmp_path: Path,
) -> None:
    """无匹配 row 的 covered cursor 推进也会清除旧 failure row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        latest = _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_B",
            marker="unmatched",
        )

        def write_failure(transaction: HostTransaction) -> None:
            """写入测试用旧 projection failure。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            write_projection_failure(
                transaction,
                "consumer",
                failed_event_sequence=latest.event_sequence,
                failed_event_id=latest.event_id,
                error_code="TEST_FAILURE",
                error_message="previous failure",
                now="2026-06-18T00:00:00+00:00",
            )

        store.transaction_runner.run_write(write_failure)
        consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=10
        )
        failure = store.transaction_runner.run_write(
            lambda transaction: read_projection_failure(transaction, "consumer")
        )
        assert result.events_scanned == 1
        assert result.events_matched == 0
        assert result.finished_cursor == latest.event_sequence
        assert failure is None


def test_runner_target_before_next_matching_row_advances_to_target_without_apply(
    tmp_path: Path,
) -> None:
    """target cursor 位于下一条匹配 row 之前时，runner 推进到 target 且不 apply。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        target = _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_B",
            marker="target",
        )
        _append_event(
            store.transaction_runner,
            event_id="event-2",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="future-match",
        )
        consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"),
            limit=10,
            max_event_sequence=target.event_sequence,
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        assert consumer.applied_events == []
        assert result.events_scanned == 1
        assert result.events_matched == 0
        assert result.finished_cursor == target.event_sequence
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == target.event_sequence
        assert checkpoint.checkpoint_event_id == target.event_id


def test_matching_row_failure_does_not_advance_past_failed_row(
    tmp_path: Path,
) -> None:
    """匹配 row apply 失败时 checkpoint 不会越过失败 row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_B",
            marker="unmatched",
        )
        failed = _append_event(
            store.transaction_runner,
            event_id="event-2",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="failed",
        )
        _append_event(
            store.transaction_runner,
            event_id="event-3",
            event_class=EventClass.CANONICAL_FACT,
            event_type="TYPE_A",
            marker="not-reached",
        )
        consumer = _FakeConsumer(
            "consumer",
            _canonical_type_filter("TYPE_A"),
            fail_event_ids=frozenset({"event-2"}),
        )
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=10
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        failure = store.transaction_runner.run_write(
            lambda transaction: read_projection_failure(transaction, "consumer")
        )
        assert [event.event_id for event in consumer.applied_events] == ["event-2"]
        assert result.failures == 1
        assert result.finished_cursor == 0
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence < failed.event_sequence
        assert failure is not None
        assert failure.failed_event_sequence == failed.event_sequence
        assert failure.failed_event_id == failed.event_id


def test_run_once_limit_caps_steps_when_matching_events_remain(
    tmp_path: Path,
) -> None:
    """dense matching rows 下 limit 是本轮 step cap，不一次 apply 整页。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        events = tuple(
            _append_event(
                store.transaction_runner,
                event_id=f"event-{index}",
                event_class=EventClass.CANONICAL_FACT,
                event_type="TYPE_A",
                marker=f"marker-{index}",
            )
            for index in range(1, 6)
        )
        consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            ProjectionConsumerId("consumer"), limit=3
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: read_projection_checkpoint(transaction, "consumer")
        )
        assert [event.event_id for event in consumer.applied_events] == [
            "event-1",
            "event-2",
            "event-3",
        ]
        assert result.events_scanned == 3
        assert result.events_matched == 3
        assert result.events_applied == 3
        assert result.finished_cursor == events[2].event_sequence
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == events[2].event_sequence
        assert checkpoint.checkpoint_event_id == events[2].event_id


def test_runner_rejects_unknown_consumer(tmp_path: Path) -> None:
    """runner 对未注册 consumer id 结构化失败。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        consumer = _FakeConsumer("consumer", _canonical_type_filter("TYPE_A"))
        runner = ProjectionRunner(store.transaction_runner, (consumer,))
        with pytest.raises(HostDurableError):
            runner.run_once(ProjectionConsumerId("missing"), limit=1)
