"""P7 S1 contract / serializer 测试。

覆盖：

- 新增 :class:`RunInputContextSnapshotBuiltData` 注册到
  ``_DATA_CLASS_BY_TYPE``。
- ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` 序列化 / 反序列化 round-trip。
- decode 拒绝未知 / 缺失字段。
"""

from __future__ import annotations

import json

import pytest

from dayu.host._run_event_serializer import (
    _DATA_CLASS_BY_TYPE,
    deserialize_run_event_data,
    serialize_run_event_data,
)
from dayu.host.contracts import (
    RunEventType,
    RunInputContextMeta,
    RunInputContextSnapshotBuiltData,
    RunInputMessageSummary,
    RunInputToolSchemaSummary,
)


def _sample_data() -> RunInputContextSnapshotBuiltData:
    """构造 snapshot fact data 样例。

    :returns: snapshot fact data 实例。
    :raises Exception: 不主动抛出异常。
    """

    return RunInputContextSnapshotBuiltData(
        iteration_id="iter-1",
        iteration_index=0,
        attempt_index=0,
        current_user_excerpt="hello",
        current_user_content_hash="abc123",
        current_user_source_cursor=7,
        message_summaries=(
            RunInputMessageSummary(
                role="system",
                source_kind="caller_system",
                excerpt="sys",
                content_hash="h-sys",
                char_size=3,
                token_estimate=1,
            ),
            RunInputMessageSummary(
                role="user",
                source_kind="current_user",
                excerpt="hello",
                content_hash="h-user",
                char_size=5,
                token_estimate=1,
            ),
        ),
        tool_schema_summaries=(
            RunInputToolSchemaSummary(name="calc", schema_hash="sh-1"),
        ),
        context_meta=RunInputContextMeta(
            message_count=2,
            role_sequence=("system", "user"),
            total_char_size=8,
            total_token_estimate=2,
            memory_item_count=0,
            current_user_run_id="run-1",
        ),
        raw_input_messages_blob_id="blob-input",
        raw_input_messages_sha256="sha-input",
        raw_input_messages_byte_size=35,
        raw_tool_schemas_blob_id="blob-tools",
        raw_tool_schemas_sha256="sha-tools",
        raw_tool_schemas_byte_size=17,
    )


def test_run_input_context_snapshot_built_registered_in_data_class_by_type() -> None:
    """``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` 必须注册到封闭映射。"""

    assert (
        _DATA_CLASS_BY_TYPE[RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT]
        is RunInputContextSnapshotBuiltData
    )


def test_run_input_context_snapshot_built_round_trip() -> None:
    """编码 / 解码必须返回等价 dataclass。"""

    data = _sample_data()
    raw = serialize_run_event_data(
        event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
        data=data,
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
        raw=raw,
    )
    assert decoded == data


def test_run_input_context_snapshot_built_decode_rejects_invalid_fields() -> None:
    """缺失关键字段时 decode 必须 fail-fast。"""

    data = _sample_data()
    raw = serialize_run_event_data(
        event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
        data=data,
    )
    payload = json.loads(raw)
    fields = dict(payload["fields"])
    fields.pop("raw_input_messages_blob_id")
    payload["fields"] = fields
    bad_raw = json.dumps(payload)
    with pytest.raises(ValueError):
        deserialize_run_event_data(
            event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
            raw=bad_raw,
        )


def test_run_input_context_snapshot_built_optional_cursor_is_none() -> None:
    """``current_user_source_cursor`` 可为 ``None``，编码 / 解码必须保持。"""

    base = _sample_data()
    data = RunInputContextSnapshotBuiltData(
        iteration_id=base.iteration_id,
        iteration_index=base.iteration_index,
        attempt_index=base.attempt_index,
        current_user_excerpt=base.current_user_excerpt,
        current_user_content_hash=base.current_user_content_hash,
        current_user_source_cursor=None,
        message_summaries=base.message_summaries,
        tool_schema_summaries=base.tool_schema_summaries,
        context_meta=base.context_meta,
        raw_input_messages_blob_id=base.raw_input_messages_blob_id,
        raw_input_messages_sha256=base.raw_input_messages_sha256,
        raw_input_messages_byte_size=base.raw_input_messages_byte_size,
        raw_tool_schemas_blob_id=base.raw_tool_schemas_blob_id,
        raw_tool_schemas_sha256=base.raw_tool_schemas_sha256,
        raw_tool_schemas_byte_size=base.raw_tool_schemas_byte_size,
    )
    raw = serialize_run_event_data(
        event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
        data=data,
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
        raw=raw,
    )
    assert decoded == data
