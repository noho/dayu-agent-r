"""P7 S2 ToolTraceJsonlSink 测试。

覆盖：

- ``append_record_line`` 每行追加并 fsync。
- 文件大小达到 ~10MB 触发滚动。
- ``write_raw_payload_blob`` 通过 tmp + ``os.replace`` 原子改名。
- ``_scrub_provider_secret`` 替换敏感键。
- ``compute_idempotency_key`` 输入相同则结果相同，关键字段任一变化结果变化。
"""

from __future__ import annotations

from pathlib import Path

from dayu.host._tool_trace_jsonl_sink import (
    ToolTraceJsonlSink,
    _scrub_provider_secret,
    compute_idempotency_key,
)

_LARGE_FILE_THRESHOLD: int = 10 * 1024 * 1024
_DUMMY_LINE_BYTES: int = 1024


def test_append_record_line_writes_one_line_per_call(tmp_path: Path) -> None:
    """每次调用追加一行 JSONL。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    p1 = sink.append_record_line(session_id="s1", record={"k": 1})
    p2 = sink.append_record_line(session_id="s1", record={"k": 2})
    assert p1 == p2
    lines = p1.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"k": 1' in lines[0]
    assert '"k": 2' in lines[1]


def test_append_record_line_rolls_when_file_exceeds_threshold(
    tmp_path: Path,
) -> None:
    """文件大小超过阈值后写入下一个分片。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    target_dir = tmp_path / "sessions" / "s1"
    target_dir.mkdir(parents=True, exist_ok=True)
    first = target_dir / "tool_calls_000001.jsonl"
    first.write_bytes(b"x" * (_LARGE_FILE_THRESHOLD + _DUMMY_LINE_BYTES))
    rolled_path = sink.append_record_line(session_id="s1", record={"k": "v"})
    assert rolled_path.name == "tool_calls_000002.jsonl"


def test_write_raw_payload_blob_atomic_replace(tmp_path: Path) -> None:
    """raw payload 写入完成后 tmp 文件不存在，目标文件就位。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    final_path = sink.write_raw_payload_blob(
        run_id="r1",
        iteration_id="i1",
        blob_id="abc",
        payload_text='{"hello": "world"}',
    )
    assert final_path.exists()
    assert final_path.read_text(encoding="utf-8") == '{"hello": "world"}'
    tmp_path_file = final_path.with_suffix(".json.tmp")
    assert not tmp_path_file.exists()


def test_scrub_provider_secret_replaces_known_keys() -> None:
    """敏感字段被替换为 ``"***"``，非敏感字段保留原值。"""

    payload = {
        "Authorization": "Bearer xxx",
        "api_key": "sk-yyy",
        "headers": {
            "x-api-key": "secret",
            "x-other": "ok",
        },
        "messages": [{"content": "hi", "Cookie": "c=1"}],
    }
    scrubbed = _scrub_provider_secret(payload)
    assert isinstance(scrubbed, dict)
    assert scrubbed["Authorization"] == "***"
    assert scrubbed["api_key"] == "***"
    headers = scrubbed["headers"]
    assert isinstance(headers, dict)
    assert headers["x-api-key"] == "***"
    assert headers["x-other"] == "ok"
    messages = scrubbed["messages"]
    assert isinstance(messages, list)
    first = messages[0]
    assert isinstance(first, dict)
    assert first["Cookie"] == "***"
    assert first["content"] == "hi"


def test_compute_idempotency_key_is_deterministic() -> None:
    """同样输入产出相同 key；任何字段变化产出不同 key。"""

    base = compute_idempotency_key(
        schema_version="tool_trace_v2_host",
        trace_type="tool_call",
        run_id="r1",
        iteration_id="iter-1",
        tool_call_id="t1",
        source_event_position=42,
        record_role="primary",
    )
    same = compute_idempotency_key(
        schema_version="tool_trace_v2_host",
        trace_type="tool_call",
        run_id="r1",
        iteration_id="iter-1",
        tool_call_id="t1",
        source_event_position=42,
        record_role="primary",
    )
    diff_position = compute_idempotency_key(
        schema_version="tool_trace_v2_host",
        trace_type="tool_call",
        run_id="r1",
        iteration_id="iter-1",
        tool_call_id="t1",
        source_event_position=43,
        record_role="primary",
    )
    diff_role = compute_idempotency_key(
        schema_version="tool_trace_v2_host",
        trace_type="tool_call",
        run_id="r1",
        iteration_id="iter-1",
        tool_call_id="t1",
        source_event_position=42,
        record_role="secondary",
    )
    assert base == same
    assert base != diff_position
    assert base != diff_role
    assert len(base) == 32
