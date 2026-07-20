"""Host read API terminal text policy 投影测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.api import HostEvent, HostEventKind, HostTerminalStatus
from dayu.host.durable.codec import canonical_json_dumps, format_utc_timestamp
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.outbox import build_outbox_terminal_item_row
from dayu.host.projection import projection_event_view_from_row
from dayu.host.read_api import _host_event_from_row

_SESSION_ID = "session-terminal-policy"
_RUN_ID = "run-terminal-policy"
_ATTEMPT_ID = "attempt-terminal-policy"
_EXECUTION_ID = "execution-terminal-policy"
_TIMESTAMP = format_utc_timestamp(datetime(2026, 6, 12, tzinfo=UTC))


def test_failed_terminal_projection_never_builds_final_answer(tmp_path: Path) -> None:
    """RUN_FAILED 投影不把 diagnostic payload 当成 final answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: FAILED HostEvent 携带 final answer 时抛出。
    """

    event = _project_terminal_event(
        tmp_path,
        event_type="RUN_FAILED",
        payload={
            "message": "provider failed",
            "final_answer": "must not be displayed",
            "content": "must not be displayed",
            "terminal_summary_ref": "missing-ref",
            "terminal_summary_digest": "sha256:missing",
        },
    )

    assert event.kind is HostEventKind.FAILED
    assert event.terminal_status is HostTerminalStatus.FAILED
    assert event.final_answer is None
    assert event.error_message == "provider failed"
    assert event.cancel_reason is None


def test_failed_terminal_projection_appends_correlation_suffix(
    tmp_path: Path,
) -> None:
    """live watcher 与 outbox fallback 使用相同 terminal 诊断后缀。"""

    payload: dict[str, JsonValue] = {
        "message": "provider failed",
        "provider_request_id": None,
        "client_correlation_id": "client-fallback",
    }
    row = _row("RUN_FAILED", payload)
    original_payload_json = row.payload_json

    event = _project_terminal_row(tmp_path, row)
    outbox_row = None
    with open_host_durable_store(_options(tmp_path / "outbox")) as store:
        outbox_row = store.transaction_runner.run_read(
            lambda transaction: build_outbox_terminal_item_row(
                transaction,
                projection_event_view_from_row(row),
            )
        )

    assert outbox_row is not None
    assert event.error_message == (
        "provider failed\nclient_correlation_id=client-fallback"
    )
    assert outbox_row.error_message == event.error_message
    assert row.payload_json == original_payload_json
    assert payload["message"] == "provider failed"


def test_cancelled_terminal_projection_never_builds_final_answer(tmp_path: Path) -> None:
    """RUN_CANCELLED 投影不把 cancellation reason 当成 final answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: CANCELLED HostEvent 携带 final answer 时抛出。
    """

    event = _project_terminal_event(
        tmp_path,
        event_type="RUN_CANCELLED",
        payload={
            "reason": "user_stop",
            "final_answer": "must not be displayed",
            "content": "must not be displayed",
            "terminal_summary_ref": "missing-ref",
            "terminal_summary_digest": "sha256:missing",
        },
    )

    assert event.kind is HostEventKind.CANCELLED
    assert event.terminal_status is HostTerminalStatus.CANCELLED
    assert event.final_answer is None
    assert event.error_message is None
    assert event.cancel_reason == "user_stop"


def test_lost_terminal_projection_never_builds_final_answer(tmp_path: Path) -> None:
    """RUN_LOST 投影不把 lifecycle diagnostic 当成 final answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: LOST HostEvent 携带 final answer 时抛出。
    """

    event = _project_terminal_event(
        tmp_path,
        event_type="RUN_LOST",
        payload={
            "message": "worker lost",
            "final_answer": "must not be displayed",
            "content": "must not be displayed",
            "terminal_summary_ref": "missing-ref",
            "terminal_summary_digest": "sha256:missing",
        },
    )

    assert event.kind is HostEventKind.LOST
    assert event.terminal_status is HostTerminalStatus.LOST
    assert event.final_answer is None
    assert event.error_message == "worker lost"
    assert event.cancel_reason is None


def test_succeeded_terminal_projection_reads_inline_final_answer(
    tmp_path: Path,
) -> None:
    """RUN_SUCCEEDED inline answer 经 required owner 投影为 HostEvent。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: inline success 未生成完整 final answer 时抛出。
    """

    event = _project_terminal_event(
        tmp_path,
        event_type="RUN_SUCCEEDED",
        payload={
            "final_answer": "inline answer",
            "filtered": True,
            "degraded": False,
            "finish_reason": "stop",
        },
    )

    assert event.kind is HostEventKind.SUCCEEDED
    assert event.final_answer is not None
    assert event.final_answer.content == "inline answer"
    assert event.final_answer.filtered is True
    assert event.final_answer.degraded is False
    assert event.final_answer.finish_reason == "stop"


def test_succeeded_terminal_projection_reads_descriptor_content_and_canonical_metadata(
    tmp_path: Path,
) -> None:
    """descriptor-only success 的 content 与 canonical metadata 分别同源投影。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: HostEvent content 或 metadata source 漂移时抛出。
    """

    event = _project_descriptor_succeeded_event(
        tmp_path,
        artifact_payload={
            "content": "descriptor answer",
            "filtered": False,
            "degraded": True,
            "finish_reason": "artifact-must-not-own-metadata",
        },
        canonical_digest_override=None,
    )

    assert event.final_answer is not None
    assert event.final_answer.content == "descriptor answer"
    assert event.final_answer.filtered is True
    assert event.final_answer.degraded is False
    assert event.final_answer.finish_reason == "stop"


def test_succeeded_terminal_projection_rejects_non_text_finish_reason(
    tmp_path: Path,
) -> None:
    """succeeded HostEvent read 拒绝 canonical 非文本 finish_reason。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: canonical metadata 未 fail closed 时抛出。
    """

    with pytest.raises(HostDurableError, match="finish_reason"):
        _project_terminal_event(
            tmp_path,
            event_type="RUN_SUCCEEDED",
            payload={
                "final_answer": "inline answer",
                "filtered": False,
                "degraded": False,
                "finish_reason": 123,
            },
        )


@pytest.mark.parametrize(
    ("artifact_payload", "digest_override", "expected_fragment"),
    (
        ({}, None, "content is missing"),
        ({"content": "  "}, None, "content is blank"),
        ({"content": 7}, None, "content must be text"),
        (
            {"content": "answer"},
            "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "descriptor digest mismatch",
        ),
    ),
)
def test_succeeded_terminal_projection_fails_closed_for_descriptor_errors(
    tmp_path: Path,
    artifact_payload: JsonValue,
    digest_override: str | None,
    expected_fragment: str,
) -> None:
    """HostEvent success projection 对 descriptor/content 损坏 fail closed。

    :param tmp_path: pytest 临时目录。
    :param artifact_payload: terminal artifact JSON。
    :param digest_override: canonical digest 覆盖值。
    :param expected_fragment: 期望错误片段。
    :returns: ``None``。
    :raises AssertionError: descriptor error 未分类时抛出。
    """

    with pytest.raises(HostDurableError, match=expected_fragment):
        _project_descriptor_succeeded_event(
            tmp_path,
            artifact_payload=artifact_payload,
            canonical_digest_override=digest_override,
        )


@pytest.mark.parametrize(
    "payload",
    (
        {"terminal_summary_ref": "only-ref"},
        {
            "terminal_summary_ref": "missing-ref",
            "terminal_summary_digest": "sha256:missing",
        },
    ),
)
def test_succeeded_terminal_projection_rejects_missing_descriptor_material(
    tmp_path: Path,
    payload: dict[str, JsonValue],
) -> None:
    """HostEvent success projection 拒绝单边或不存在的 descriptor。

    :param tmp_path: pytest 临时目录。
    :param payload: malformed canonical success payload。
    :returns: ``None``。
    :raises AssertionError: malformed descriptor 未 fail closed 时抛出。
    """

    payload.update(
        {
            "filtered": False,
            "degraded": False,
            "finish_reason": "stop",
        }
    )
    with pytest.raises(HostDurableError):
        _project_terminal_event(
            tmp_path,
            event_type="RUN_SUCCEEDED",
            payload=payload,
        )


def _project_terminal_event(
    tmp_path: Path, *, event_type: str, payload: dict[str, JsonValue]
) -> HostEvent:
    """投影测试用 terminal EventLog row。

    :param tmp_path: pytest 临时目录。
    :param event_type: terminal event type。
    :param payload: terminal payload。
    :returns: 投影后的 HostEvent。
    """

    return _project_terminal_row(tmp_path, _row(event_type, payload))


def _project_descriptor_succeeded_event(
    tmp_path: Path,
    *,
    artifact_payload: JsonValue,
    canonical_digest_override: str | None,
) -> HostEvent:
    """写入 terminal descriptor 并投影 descriptor-only success。

    :param tmp_path: pytest 临时目录。
    :param artifact_payload: terminal SQLite payload JSON。
    :param canonical_digest_override: canonical event digest 覆盖值。
    :returns: succeeded HostEvent。
    :raises HostDurableError: descriptor 或 final answer contract 非法时抛出。
    """

    event: HostEvent | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="terminal-policy-descriptor",
                    payload_id="terminal-policy-sqlite-payload",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=artifact_payload,
                ),
            )
        )
        payload: dict[str, JsonValue] = {
            "terminal_summary_ref": descriptor.payload_ref,
            "terminal_summary_digest": (
                descriptor.payload_digest
                if canonical_digest_override is None
                else canonical_digest_override
            ),
            "filtered": True,
            "degraded": False,
            "finish_reason": "stop",
        }
        event = store.transaction_runner.run_read(
            lambda transaction: _host_event_from_row(
                transaction,
                _row("RUN_SUCCEEDED", payload),
            )
        )
    assert event is not None
    return event


def _project_terminal_row(tmp_path: Path, row: EventLogRow) -> HostEvent:
    """投影测试用 terminal EventLog row。

    :param tmp_path: pytest 临时目录。
    :param row: terminal EventLog row。
    :returns: 投影后的 HostEvent。
    """

    event: HostEvent | None = None
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> HostEvent:
            """执行 read API terminal 投影。

            :param transaction: Host transaction。
            :returns: 投影后的 HostEvent。
            """

            return _host_event_from_row(transaction, row)

        event = store.transaction_runner.run_read(operation)
    assert event is not None
    return event


def _row(event_type: str, payload: dict[str, JsonValue]) -> EventLogRow:
    """构造 terminal EventLog row。

    :param event_type: terminal event type。
    :param payload: terminal payload。
    :returns: EventLog row。
    """

    return EventLogRow(
        event_sequence=1,
        event_id=f"event-{event_type.lower()}",
        event_body_digest="sha256:terminal-policy",
        event_class=EventClass.CANONICAL_FACT,
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        execution_id=_EXECUTION_ID,
        event_type=event_type,
        occurred_at=_TIMESTAMP,
        actor="pytest",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json=canonical_json_dumps(payload),
        payload_ref=None,
        payload_digest=None,
        appended_at=_TIMESTAMP,
    )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )
