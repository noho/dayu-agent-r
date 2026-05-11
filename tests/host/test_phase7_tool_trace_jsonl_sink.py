"""P7 S2 ToolTraceJsonlSink 测试。

覆盖：

- ``append_record_line`` 每行追加并 fsync。
- 文件大小达到 ~10MB 触发滚动。
- ``write_raw_payload_blob`` 通过 tmp + ``os.replace`` 原子改名。
- ``_scrub_provider_secret`` 替换敏感键与字符串 header。
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
    first = sink.append_record_line(session_id="s1", record={"seed": True})
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


def test_trace_paths_encode_logical_ids_inside_root(tmp_path: Path) -> None:
    """session/run/iteration/blob 逻辑 id 不得影响 trace root 外路径。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    jsonl_path = sink.append_record_line(
        session_id="../s/..\\evil",
        record={"k": "v"},
    )
    blob_path = sink.write_raw_payload_blob(
        run_id="../run/..\\evil",
        iteration_id="",
        blob_id="../blob/..\\evil",
        payload_text="{}",
    )

    root = tmp_path.resolve()
    assert jsonl_path.resolve().relative_to(root)
    assert blob_path.resolve().relative_to(root)
    assert ".." not in jsonl_path.relative_to(root).as_posix()
    assert ".." not in blob_path.relative_to(root).as_posix()


def test_trace_paths_hash_long_logical_ids_inside_root(tmp_path: Path) -> None:
    """超长逻辑 id 使用稳定短 segment，避免单段文件名过长。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    long_id = "x" * 2048

    jsonl_path = sink.append_record_line(
        session_id=long_id,
        record={"k": "v"},
    )
    blob_path = sink.write_raw_payload_blob(
        run_id=long_id,
        iteration_id=long_id,
        blob_id=long_id,
        payload_text="{}",
    )

    root = tmp_path.resolve()
    assert jsonl_path.resolve().relative_to(root)
    assert blob_path.resolve().relative_to(root)
    assert all(len(part) <= 120 for part in jsonl_path.relative_to(root).parts)
    assert all(len(part) <= 255 for part in blob_path.relative_to(root).parts)


def test_scrub_provider_secret_replaces_known_keys() -> None:
    """敏感字段被替换为 ``"***"``，非敏感字段保留原值。"""

    payload = {
        "Authorization": "Bearer xxx",
        "api_key": "sk-yyy",
        "openai-organization": "org-public-id",
        "anthropic-version": "2023-06-01",
        "client_secret": "client-secret",
        "private_key": "private-key",
        "password": "password",
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
    assert scrubbed["openai-organization"] == "org-public-id"
    assert scrubbed["anthropic-version"] == "2023-06-01"
    assert scrubbed["client_secret"] == "***"
    assert scrubbed["private_key"] == "***"
    assert scrubbed["password"] == "***"
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


def test_scrub_provider_secret_scrubs_header_text_and_keeps_runtime_fields() -> None:
    """provider raw payload 中的字符串 header 清洗，运行期能力字段保留。"""

    payload = {
        "message": (
            "Authorization: Bearer sk-live\n"
            "x-api-key: sk-x\n"
            "cookie: sid=secret\n"
            "API key = sk-api\n"
            "client_secret=sk-client\n"
            "private_key: sk-private\n"
            "password: sk-password\n"
            "cursor: cursor-raw\n"
            "scope_token: scope-raw\n"
            "token: ordinary-token\n"
            "anthropic-version: 2023-06-01\n"
            "openai-organization: org-public-id"
        ),
        "cursor": "cursor-raw",
        "scope_token": "scope-raw",
        "token": "ordinary-token",
        "anthropic-version": "2023-06-01",
        "openai-organization": "org-public-id",
        "nested": [
            {
                "debug": (
                    "Authorization=Bearer nested-secret, "
                    "token=ordinary-token"
                )
            }
        ],
    }
    scrubbed = _scrub_provider_secret(payload)
    assert isinstance(scrubbed, dict)
    assert scrubbed["cursor"] == "cursor-raw"
    assert scrubbed["scope_token"] == "scope-raw"
    assert scrubbed["token"] == "ordinary-token"
    assert scrubbed["anthropic-version"] == "2023-06-01"
    assert scrubbed["openai-organization"] == "org-public-id"
    message = scrubbed["message"]
    assert isinstance(message, str)
    assert "Authorization: ***" in message
    assert "x-api-key: ***" in message
    assert "cookie: ***" in message
    assert "API key = ***" in message
    assert "client_secret=***" in message
    assert "private_key: ***" in message
    assert "password: ***" in message
    assert "cursor: cursor-raw" in message
    assert "scope_token: scope-raw" in message
    assert "token: ordinary-token" in message
    assert "anthropic-version: 2023-06-01" in message
    assert "openai-organization: org-public-id" in message
    assert "sk-live" not in message
    assert "sk-x" not in message
    assert "sid=secret" not in message
    assert "sk-api" not in message
    assert "sk-client" not in message
    assert "sk-private" not in message
    assert "sk-password" not in message
    nested = scrubbed["nested"]
    assert isinstance(nested, list)
    first = nested[0]
    assert isinstance(first, dict)
    debug = first["debug"]
    assert isinstance(debug, str)
    assert debug == "Authorization=***, token=ordinary-token"


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
