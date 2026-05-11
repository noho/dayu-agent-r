"""P7 S1 schema bootstrap 测试。

确认：

- P7 不向 SQLite 引入 ``host_tool_trace_*`` 任何新表（trace 完全走文件系统）。
- ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` fact 只保存 raw payload 引用，不再
  内联大体积 raw JSON。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._host_storage_transaction import HostStorage
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunInputContextMeta,
    RunInputContextSnapshotBuiltData,
    RunInputMessageSummary,
    RunInputToolSchemaSummary,
)


def test_no_tool_trace_tables_added_to_sqlite_schema() -> None:
    """P7 不允许在 SQLite 中新增 ``host_tool_trace_*`` 任何表。"""

    storage = HostStorage(database_path=":memory:")
    try:
        storage.open()
        open_durable_event_store(storage)
        connection = storage._connection  # noqa: SLF001
        assert connection is not None
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {row[0] for row in rows}
        offenders = {n for n in names if n.startswith("host_tool_trace")}
        assert offenders == set(), f"unexpected tool trace tables: {offenders}"
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_run_event_data_column_keeps_bounded_raw_payload_refs() -> None:
    """``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` round-trip 只保存 bounded refs。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        data = RunInputContextSnapshotBuiltData(
            iteration_id="iter-1",
            iteration_index=0,
            attempt_index=0,
            current_user_excerpt="hello",
            current_user_content_hash="h",
            current_user_source_cursor=1,
            message_summaries=(
                RunInputMessageSummary(
                    role="user",
                    source_kind="current_user",
                    excerpt="hello",
                    content_hash="h",
                    char_size=5,
                    token_estimate=1,
                ),
            ),
            tool_schema_summaries=(
                RunInputToolSchemaSummary(name="t", schema_hash="sh"),
            ),
            context_meta=RunInputContextMeta(
                message_count=1,
                role_sequence=("user",),
                total_char_size=5,
                total_token_estimate=1,
                memory_item_count=0,
                current_user_run_id="r1",
            ),
            raw_input_messages_blob_id="blob-input",
            raw_input_messages_sha256="sha-input",
            raw_input_messages_byte_size=256 * 1024,
            raw_tool_schemas_blob_id="blob-tools",
            raw_tool_schemas_sha256="sha-tools",
            raw_tool_schemas_byte_size=128 * 1024,
        )
        draft = RunEventDraft(
            run_id="r1",
            session_id="s1",
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.HOST,
            type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
            occurred_at=datetime.now(timezone.utc),
            data=data,
            source_engine_event_id=None,
        )
        appended = await store.append(draft)
        assert appended.run_id == "r1"
        rows = list(store.fetch_events_by_position(after=None, limit=10))
        assert len(rows) == 1
        _, event = rows[0]
        assert isinstance(event.data, RunInputContextSnapshotBuiltData)
        assert event.data.raw_input_messages_blob_id == "blob-input"
        assert event.data.raw_tool_schemas_blob_id == "blob-tools"
        assert event.data.raw_input_messages_byte_size == 256 * 1024
        assert event.data.raw_tool_schemas_byte_size == 128 * 1024
    finally:
        storage.close()
