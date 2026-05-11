"""P7 S2 ToolTraceObserver 派发逻辑测试。

覆盖：

- ``TOOL_CALL_REQUESTED`` + ``TOOL_RESULT_ACCEPTED`` 同 batch 配对生成
  ``tool_call`` record。
- 仅 ``TOOL_CALL_REQUESTED`` 而无 ``TOOL_RESULT_ACCEPTED`` 抛
  :class:`ProjectionSchemaError`。
- ``RUNNER_USAGE_RECORDED`` 派发为 ``iteration_usage``。
- ``FINAL_ANSWER`` 派发为 ``final_response``，``iteration_id`` 为空字符串。
- ``PROVIDER_PROTOCOL_ERROR`` raw_payload 缺失时写入
  ``omitted_no_payload``；带 payload 时执行 secret scrub。
- ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` 写入 2 个 raw_payloads 文件 + 1
  条 JSONL。
- 同一序列重复 ``process`` 产出相同 ``idempotency_key``。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

import pytest

from dayu.contracts import JsonValue
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
)
from dayu.engine import (
    FinalAnswerData,
    FinishReason,
    ProviderProtocolErrorData,
    RunnerUsageData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)
from dayu.host._event_observer import ProjectionEventEnvelope
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import GlobalEventPosition
from dayu.host._run_input_raw_payload_store import (
    RunInputRawPayloadKind,
    RunInputRawPayloadReadError,
    RunInputRawPayloadRefs,
    RunInputRawPayloadWriteSet,
    ensure_run_input_raw_payload_schema,
    get_run_input_raw_payload,
    put_run_input_raw_payloads,
)
from dayu.host._tool_trace_jsonl_sink import ToolTraceJsonlSink
from dayu.host._tool_trace_projection import (
    ProjectionSchemaError,
    ToolTraceObserver,
)
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventData,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunInputContextMeta,
    RunInputContextSnapshotBuiltData,
    RunInputMessageSummary,
    RunInputToolSchemaSummary,
)

_RUN_ID: str = "r1"
_SESSION_ID: str = "s1"


def _utc() -> datetime:
    """当前 UTC 时间。

    :returns: 时区感知 datetime。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _envelope(
    *, position: int, event_type: RunEventType, data: RunEventData, sequence: int = 0
) -> ProjectionEventEnvelope:
    """构造 ProjectionEventEnvelope。

    :param position: 全局 position 值。
    :param event_type: RunEventType。
    :param data: 事件 data。
    :param sequence: cursor sequence。
    :returns: envelope。
    :raises Exception: 不主动抛出异常。
    """

    event = RunEvent(
        run_id=_RUN_ID,
        session_id=_SESSION_ID,
        cursor=RunEventCursor(sequence=sequence),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=event_type,
        occurred_at=_utc(),
        data=data,
        source_engine_event_id=None,
    )
    return ProjectionEventEnvelope(
        position=GlobalEventPosition(value=position),
        event=event,
    )


def _completed_outcome() -> ToolCompletedOutcome:
    """构造 completed outcome。

    :returns: outcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=cast(Literal[True], True),
            value={"v": 1},
            meta=None,
        )
    )


def _failed_outcome() -> ToolFailedOutcome:
    """构造 failed outcome。

    :returns: outcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=cast(Literal[False], False),
            error="boom",
            message="bad",
            hint=None,
            meta=None,
        )
    )


def _read_jsonl_lines(root: Path) -> list[dict[str, JsonValue]]:
    """读取 session 目录下所有 JSONL 行。

    :param root: sink root_path。
    :returns: 解析后的 record list。
    :raises Exception: 不主动抛出异常。
    """

    target_dir = root / "sessions" / _SESSION_ID
    if not target_dir.exists():
        return []
    out: list[dict[str, JsonValue]] = []
    for path in sorted(target_dir.glob("tool_calls_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                out.append(json.loads(line))
    return out


@pytest.mark.asyncio
async def test_tool_call_paired_emits_record(tmp_path: Path) -> None:
    """同 batch ``TOOL_CALL_REQUESTED`` + ``TOOL_RESULT_ACCEPTED`` 派发一行。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    requested = _envelope(
        position=1,
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        data=ToolCallRequestedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            arguments={"text": "hi"},
            index_in_iteration=0,
            provider_state=None,
        ),
    )
    accepted = _envelope(
        position=2,
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            index_in_iteration=0,
            outcome=_completed_outcome(),
        ),
    )
    await observer.process(tx=cast(object, None), batch=(requested, accepted))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 1
    rec = lines[0]
    assert rec["trace_type"] == "tool_call"
    assert rec["tool_call_id"] == "call-1"
    assert rec["outcome_kind"] == "completed"


@pytest.mark.asyncio
async def test_tool_call_trace_scrubs_credentials_and_retains_capabilities(
    tmp_path: Path,
) -> None:
    """trace 普通工具 payload 只清洗凭证并保留 cursor / scope_token。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    requested = _envelope(
        position=1,
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        data=ToolCallRequestedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="fetch_more",
            arguments={
                "API_KEY": "sk-argument",
                "debug_text": "Authorization: Bearer sk-argument",
                "cursor": "cursor-argument",
                "scope_token": "scope-argument",
                "token": "ordinary-token",
            },
            index_in_iteration=0,
            provider_state=None,
        ),
    )
    accepted = _envelope(
        position=2,
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="fetch_more",
            index_in_iteration=0,
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=cast(Literal[True], True),
                    value={
                        "api_key": "sk-result",
                        "debug_text": "x-api-key: sk-result-text",
                        "cursor": "cursor-result",
                        "scope_token": "scope-result",
                        "token": "ordinary-result-token",
                    },
                    meta=None,
                )
            ),
        ),
    )
    await observer.process(tx=cast(object, None), batch=(requested, accepted))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 1
    arguments = lines[0]["arguments_json"]
    result_value = lines[0]["result_value_json"]
    assert isinstance(arguments, str)
    assert isinstance(result_value, str)
    parsed_arguments = json.loads(arguments)
    parsed_result = json.loads(result_value)
    assert parsed_arguments["API_KEY"] == "***"
    assert parsed_arguments["debug_text"] == "Authorization: ***"
    assert parsed_arguments["cursor"] == "cursor-argument"
    assert parsed_arguments["scope_token"] == "scope-argument"
    assert parsed_arguments["token"] == "ordinary-token"
    assert parsed_result["api_key"] == "***"
    assert parsed_result["debug_text"] == "x-api-key: ***"
    assert parsed_result["cursor"] == "cursor-result"
    assert parsed_result["scope_token"] == "scope-result"
    assert parsed_result["token"] == "ordinary-result-token"


@pytest.mark.asyncio
async def test_tool_call_missing_accepted_raises(tmp_path: Path) -> None:
    """缺失 ``TOOL_RESULT_ACCEPTED`` 抛 ProjectionSchemaError。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    requested = _envelope(
        position=1,
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        data=ToolCallRequestedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            arguments={},
            index_in_iteration=0,
            provider_state=None,
        ),
    )
    with pytest.raises(ProjectionSchemaError):
        await observer.process(tx=cast(object, None), batch=(requested,))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_tool_call_failed_outcome_records_error(tmp_path: Path) -> None:
    """failed outcome 写入 ``failure_error`` / ``failure_message``。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    requested = _envelope(
        position=1,
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        data=ToolCallRequestedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            arguments={},
            index_in_iteration=0,
            provider_state=None,
        ),
    )
    accepted = _envelope(
        position=2,
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            index_in_iteration=0,
            outcome=_failed_outcome(),
        ),
    )
    await observer.process(tx=cast(object, None), batch=(requested, accepted))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert lines[0]["outcome_kind"] == "failed"
    assert lines[0]["failure_error"] == "boom"
    assert lines[0]["failure_message"] == "bad"


@pytest.mark.asyncio
async def test_iteration_usage_emits_record(tmp_path: Path) -> None:
    """``RUNNER_USAGE_RECORDED`` 派发 ``iteration_usage``。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    env = _envelope(
        position=5,
        event_type=RunEventType.RUNNER_USAGE_RECORDED,
        data=RunnerUsageData(
            iteration_id="iter-1",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        ),
    )
    await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["trace_type"] == "iteration_usage"
    assert lines[0]["prompt_tokens"] == 10
    assert lines[0]["total_tokens"] == 30


@pytest.mark.asyncio
async def test_final_answer_emits_record(tmp_path: Path) -> None:
    """``FINAL_ANSWER`` 派发 ``final_response``，``iteration_id`` 为空。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    env = _envelope(
        position=9,
        event_type=RunEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content="ok",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
    )
    await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert lines[0]["trace_type"] == "final_response"
    assert lines[0]["iteration_id"] == ""
    assert lines[0]["content"] == "ok"
    assert lines[0]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_provider_protocol_error_omitted_payload(tmp_path: Path) -> None:
    """``raw_payload`` 为 ``None`` 时 fallback 到 omitted_no_payload。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    env = _envelope(
        position=3,
        event_type=RunEventType.PROVIDER_PROTOCOL_ERROR,
        data=ProviderProtocolErrorData(
            iteration_id="iter-1",
            error_code="bad",
            message="x",
            provider_request_id=None,
            raw_payload=None,
        ),
    )
    await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    raw = lines[0]["raw_payload_json"]
    assert isinstance(raw, str)
    assert json.loads(raw) == {"reason": "omitted_no_payload"}


@pytest.mark.asyncio
async def test_provider_protocol_error_scrubs_secret(tmp_path: Path) -> None:
    """raw payload 中敏感字段被替换为 ``***``。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    env = _envelope(
        position=4,
        event_type=RunEventType.PROVIDER_PROTOCOL_ERROR,
        data=ProviderProtocolErrorData(
            iteration_id="iter-1",
            error_code="bad",
            message="x",
            provider_request_id=None,
            raw_payload={"Authorization": "Bearer abc", "msg": "ok"},
        ),
    )
    await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    raw = lines[0]["raw_payload_json"]
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert parsed["Authorization"] == "***"
    assert parsed["msg"] == "ok"


def _snapshot_data(*, refs: RunInputRawPayloadRefs) -> RunInputContextSnapshotBuiltData:
    """构造 RunInputContextSnapshotBuiltData。

    :returns: data。
    :raises Exception: 不主动抛出异常。
    """

    return RunInputContextSnapshotBuiltData(
        iteration_id="iter-1",
        iteration_index=0,
        attempt_index=0,
        current_user_excerpt="hi",
        current_user_content_hash="hash",
        current_user_source_cursor=3,
        message_summaries=(
            RunInputMessageSummary(
                role="user",
                source_kind="current_user",
                excerpt="hi",
                content_hash="h1",
                char_size=2,
                token_estimate=1,
            ),
        ),
        tool_schema_summaries=(RunInputToolSchemaSummary(name="echo", schema_hash="sh"),),
        context_meta=RunInputContextMeta(
            message_count=1,
            role_sequence=("user",),
            total_char_size=2,
            total_token_estimate=1,
            memory_item_count=0,
            current_user_run_id=_RUN_ID,
        ),
        raw_input_messages_blob_id=refs.input_messages.blob_id,
        raw_input_messages_sha256=refs.input_messages.content_sha256,
        raw_input_messages_byte_size=refs.input_messages.byte_size,
        raw_tool_schemas_blob_id=refs.tool_schemas.blob_id,
        raw_tool_schemas_sha256=refs.tool_schemas.content_sha256,
        raw_tool_schemas_byte_size=refs.tool_schemas.byte_size,
    )


@pytest.mark.asyncio
async def test_context_snapshot_writes_blob_files_and_record(tmp_path: Path) -> None:
    """context snapshot 派发 2 个 raw_payloads 文件 + 1 行 JSONL。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    storage = HostStorage(database_path=":memory:")
    storage.open()
    ensure_run_input_raw_payload_schema(storage)
    payloads = RunInputRawPayloadWriteSet(
        input_messages_json='[{"role":"user","content":"hi"}]',
        tool_schemas_json="[]",
    )
    async with storage.transaction() as tx:
        refs = put_run_input_raw_payloads(
            tx=tx,
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_index=0,
            iteration_index=0,
            iteration_id="iter-1",
            payloads=payloads,
            created_at=datetime.now(tz=timezone.utc),
        )
    observer = ToolTraceObserver(jsonl_sink=sink, raw_payload_storage=storage)
    env = _envelope(
        position=7,
        event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
        data=_snapshot_data(refs=refs),
    )
    try:
        await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
        raw_dir = tmp_path / "raw_payloads" / f"{_RUN_ID}_iter-1"
        assert (
            raw_dir / f"{refs.input_messages.blob_id}.json"
        ).read_text(encoding="utf-8").startswith("[{")
        assert (
            raw_dir / f"{refs.tool_schemas.blob_id}.json"
        ).read_text(encoding="utf-8") == "[]"
        lines = _read_jsonl_lines(tmp_path)
        assert len(lines) == 1
        rec = lines[0]
        assert rec["trace_type"] == "iteration_context_snapshot"
        assert rec["raw_input_blob_relative_path"] == (
            f"raw_payloads/{_RUN_ID}_iter-1/{refs.input_messages.blob_id}.json"
        )
        assert rec["raw_tool_schemas_blob_relative_path"] == (
            f"raw_payloads/{_RUN_ID}_iter-1/{refs.tool_schemas.blob_id}.json"
        )
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_run_input_raw_payload_rollback_leaves_no_orphan_row() -> None:
    """side-store 与外层 transaction 同生同灭，rollback 后不得残留孤儿行。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    ensure_run_input_raw_payload_schema(storage)
    payloads = RunInputRawPayloadWriteSet(
        input_messages_json="[]",
        tool_schemas_json="[]",
    )
    try:
        with pytest.raises(RuntimeError):
            async with storage.transaction() as tx:
                put_run_input_raw_payloads(
                    tx=tx,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_index=0,
                    iteration_index=0,
                    iteration_id="iter-rollback",
                    payloads=payloads,
                    created_at=datetime.now(tz=timezone.utc),
                )
                raise RuntimeError("force rollback")
        rows = storage.execute_read(
            "SELECT COUNT(*) AS count FROM run_input_raw_payloads"
        )
        assert int(rows[0]["count"]) == 0
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_context_snapshot_missing_raw_payload_fails_before_jsonl(
    tmp_path: Path,
) -> None:
    """missing side-store row 必须是 typed projection failure 且不写 trace 行。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    ensure_run_input_raw_payload_schema(storage)
    payloads = RunInputRawPayloadWriteSet(
        input_messages_json="[]",
        tool_schemas_json="[]",
    )
    async with storage.transaction() as tx:
        refs = put_run_input_raw_payloads(
            tx=tx,
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_index=0,
            iteration_index=0,
            iteration_id="iter-1",
            payloads=payloads,
            created_at=datetime.now(tz=timezone.utc),
        )
    data = replace(
        _snapshot_data(refs=refs),
        raw_input_messages_blob_id="missing-blob",
    )
    observer = ToolTraceObserver(
        jsonl_sink=ToolTraceJsonlSink(root_path=tmp_path),
        raw_payload_storage=storage,
    )
    try:
        env = _envelope(
            position=7,
            event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
            data=data,
        )
        with pytest.raises(ProjectionSchemaError, match="missing_row"):
            await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
        assert _read_jsonl_lines(tmp_path) == []
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_context_snapshot_hash_mismatch_fails_before_jsonl(
    tmp_path: Path,
) -> None:
    """hash mismatch 必须阻断 projection，避免 checkpoint 在坏读后推进。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    ensure_run_input_raw_payload_schema(storage)
    payloads = RunInputRawPayloadWriteSet(
        input_messages_json="[]",
        tool_schemas_json="[]",
    )
    async with storage.transaction() as tx:
        refs = put_run_input_raw_payloads(
            tx=tx,
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_index=0,
            iteration_index=0,
            iteration_id="iter-1",
            payloads=payloads,
            created_at=datetime.now(tz=timezone.utc),
        )
    data = replace(
        _snapshot_data(refs=refs),
        raw_input_messages_sha256="not-the-real-hash",
    )
    observer = ToolTraceObserver(
        jsonl_sink=ToolTraceJsonlSink(root_path=tmp_path),
        raw_payload_storage=storage,
    )
    try:
        env = _envelope(
            position=7,
            event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
            data=data,
        )
        with pytest.raises(ProjectionSchemaError, match="hash_mismatch"):
            await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
        assert _read_jsonl_lines(tmp_path) == []
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_run_input_raw_payload_byte_size_mismatch_is_typed_failure() -> None:
    """reader API 必须把 byte size mismatch 表达为 typed failure。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    ensure_run_input_raw_payload_schema(storage)
    payloads = RunInputRawPayloadWriteSet(
        input_messages_json="[]",
        tool_schemas_json="[]",
    )
    try:
        async with storage.transaction() as tx:
            refs = put_run_input_raw_payloads(
                tx=tx,
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                attempt_index=0,
                iteration_index=0,
                iteration_id="iter-1",
                payloads=payloads,
                created_at=datetime.now(tz=timezone.utc),
            )
        wrong_ref = replace(
            refs.input_messages,
            byte_size=refs.input_messages.byte_size + 1,
        )
        with pytest.raises(
            RunInputRawPayloadReadError,
            match="byte_size_mismatch",
        ):
            get_run_input_raw_payload(
                storage=storage,
                ref=wrong_ref,
                expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
            )
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_context_snapshot_corrupt_json_fails_before_jsonl(
    tmp_path: Path,
) -> None:
    """corrupt JSON 必须阻断 projection，禁止合成 fake raw payload。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    ensure_run_input_raw_payload_schema(storage)
    payloads = RunInputRawPayloadWriteSet(
        input_messages_json="[",
        tool_schemas_json="[]",
    )
    async with storage.transaction() as tx:
        refs = put_run_input_raw_payloads(
            tx=tx,
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_index=0,
            iteration_index=0,
            iteration_id="iter-1",
            payloads=payloads,
            created_at=datetime.now(tz=timezone.utc),
        )
    # side-store 允许持久保存原始 JSON 字符串；读取路径负责校验 JSON 合法性。
    with pytest.raises(RunInputRawPayloadReadError):
        get_run_input_raw_payload(
            storage=storage,
            ref=refs.input_messages,
            expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
        )
    observer = ToolTraceObserver(
        jsonl_sink=ToolTraceJsonlSink(root_path=tmp_path),
        raw_payload_storage=storage,
    )
    try:
        env = _envelope(
            position=7,
            event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
            data=_snapshot_data(refs=refs),
        )
        with pytest.raises(ProjectionSchemaError, match="invalid_json"):
            await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
        assert _read_jsonl_lines(tmp_path) == []
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_run_input_raw_payload_kind_mismatch_is_typed_failure() -> None:
    """reader API 必须把 kind mismatch 表达为 typed failure。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    ensure_run_input_raw_payload_schema(storage)
    payloads = RunInputRawPayloadWriteSet(
        input_messages_json="[]",
        tool_schemas_json="[]",
    )
    try:
        async with storage.transaction() as tx:
            refs = put_run_input_raw_payloads(
                tx=tx,
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                attempt_index=0,
                iteration_index=0,
                iteration_id="iter-1",
                payloads=payloads,
                created_at=datetime.now(tz=timezone.utc),
            )
        with pytest.raises(RunInputRawPayloadReadError, match="kind_mismatch"):
            get_run_input_raw_payload(
                storage=storage,
                ref=refs.input_messages,
                expected_kind=RunInputRawPayloadKind.TOOL_SCHEMAS,
            )
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_idempotency_key_stable_across_redrain(tmp_path: Path) -> None:
    """重复 process 同样 envelope 的 ``idempotency_key`` 一致。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    env = _envelope(
        position=11,
        event_type=RunEventType.RUNNER_USAGE_RECORDED,
        data=RunnerUsageData(
            iteration_id="iter-1",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
        ),
    )
    await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    await observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 2
    assert lines[0]["idempotency_key"] == lines[1]["idempotency_key"]


def _requested_env(*, position: int = 1) -> ProjectionEventEnvelope:
    """构造标准 TOOL_CALL_REQUESTED envelope。

    :param position: 全局 position。
    :returns: envelope。
    :raises Exception: 不主动抛出异常。
    """

    return _envelope(
        position=position,
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        data=ToolCallRequestedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            arguments={},
            index_in_iteration=0,
            provider_state=None,
        ),
    )


def _accepted_env(*, position: int = 2) -> ProjectionEventEnvelope:
    """构造标准 TOOL_RESULT_ACCEPTED envelope。

    :param position: 全局 position。
    :returns: envelope。
    :raises Exception: 不主动抛出异常。
    """

    return _envelope(
        position=position,
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            index_in_iteration=0,
            outcome=_completed_outcome(),
        ),
    )


@pytest.mark.asyncio
async def test_tool_call_truncation_payload_pairs_into_record(tmp_path: Path) -> None:
    """普通 accepted outcome 的 truncation payload 写入 trace 维度字段。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    accepted = _envelope(
        position=2,
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id="iter-1",
            tool_call_id="call-1",
            name="echo",
            index_in_iteration=0,
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={
                        "preview": "abc",
                        "truncation": {
                            "fetch_more_args": {
                                "cursor": "cursor-abc",
                                "limit": 10,
                                "scope_token": "scope-token",
                            },
                            "has_more": True,
                            "next_action": "fetch_more",
                            "ttl_seconds": 60,
                        },
                    },
                    meta=None,
                )
            ),
        ),
    )
    await observer.process(
        tx=cast(object, None),  # type: ignore[arg-type]
        batch=(_requested_env(), accepted),
    )
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 1
    rec = lines[0]
    assert rec["trace_type"] == "tool_call"
    assert rec["truncation_scope_token"] == "scope-token"
    assert rec["truncation_cursor"] == "cursor-abc"
    assert rec["truncation_has_more"] is True
    assert rec["truncation_limit"] == 10
