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
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

import pytest

from dayu.contracts import JsonValue
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.engine import (
    FinalAnswerData,
    FinishReason,
    ProviderProtocolErrorData,
    RunnerUsageData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)
from dayu.host._event_observer import ProjectionEventEnvelope
from dayu.host._internal_contracts import GlobalEventPosition
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
            truncation=None,
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


def test_tool_call_paired_emits_record(tmp_path: Path) -> None:
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
    observer.process(tx=cast(object, None), batch=(requested, accepted))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 1
    rec = lines[0]
    assert rec["trace_type"] == "tool_call"
    assert rec["tool_call_id"] == "call-1"
    assert rec["outcome_kind"] == "completed"


def test_tool_call_missing_accepted_raises(tmp_path: Path) -> None:
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
        observer.process(tx=cast(object, None), batch=(requested,))  # type: ignore[arg-type]


def test_tool_call_failed_outcome_records_error(tmp_path: Path) -> None:
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
    observer.process(tx=cast(object, None), batch=(requested, accepted))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert lines[0]["outcome_kind"] == "failed"
    assert lines[0]["failure_error"] == "boom"
    assert lines[0]["failure_message"] == "bad"


def test_iteration_usage_emits_record(tmp_path: Path) -> None:
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
    observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["trace_type"] == "iteration_usage"
    assert lines[0]["prompt_tokens"] == 10
    assert lines[0]["total_tokens"] == 30


def test_final_answer_emits_record(tmp_path: Path) -> None:
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
    observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert lines[0]["trace_type"] == "final_response"
    assert lines[0]["iteration_id"] == ""
    assert lines[0]["content"] == "ok"
    assert lines[0]["finish_reason"] == "stop"


def test_provider_protocol_error_omitted_payload(tmp_path: Path) -> None:
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
    observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    raw = lines[0]["raw_payload_json"]
    assert isinstance(raw, str)
    assert json.loads(raw) == {"reason": "omitted_no_payload"}


def test_provider_protocol_error_scrubs_secret(tmp_path: Path) -> None:
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
    observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    raw = lines[0]["raw_payload_json"]
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert parsed["Authorization"] == "***"
    assert parsed["msg"] == "ok"


def _snapshot_data() -> RunInputContextSnapshotBuiltData:
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
        tool_schema_summaries=(
            RunInputToolSchemaSummary(name="echo", schema_hash="sh"),
        ),
        context_meta=RunInputContextMeta(
            message_count=1,
            role_sequence=("user",),
            total_char_size=2,
            total_token_estimate=1,
            memory_item_count=0,
            current_user_run_id=_RUN_ID,
        ),
        raw_input_messages_json='[{"role":"user","content":"hi"}]',
        raw_tool_schemas_json="[]",
        raw_input_blob_id="blob_input",
        raw_tool_schemas_blob_id="blob_tools",
    )


def test_context_snapshot_writes_blob_files_and_record(tmp_path: Path) -> None:
    """context snapshot 派发 2 个 raw_payloads 文件 + 1 行 JSONL。"""

    sink = ToolTraceJsonlSink(root_path=tmp_path)
    observer = ToolTraceObserver(jsonl_sink=sink)
    env = _envelope(
        position=7,
        event_type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
        data=_snapshot_data(),
    )
    observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    raw_dir = tmp_path / "raw_payloads" / f"{_RUN_ID}_iter-1"
    assert (raw_dir / "blob_input.json").read_text(encoding="utf-8").startswith(
        "[{"
    )
    assert (raw_dir / "blob_tools.json").read_text(encoding="utf-8") == "[]"
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 1
    rec = lines[0]
    assert rec["trace_type"] == "iteration_context_snapshot"
    assert rec["raw_input_blob_relative_path"] == (
        f"raw_payloads/{_RUN_ID}_iter-1/blob_input.json"
    )
    assert rec["raw_tool_schemas_blob_relative_path"] == (
        f"raw_payloads/{_RUN_ID}_iter-1/blob_tools.json"
    )


def test_idempotency_key_stable_across_redrain(tmp_path: Path) -> None:
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
    observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    observer.process(tx=cast(object, None), batch=(env,))  # type: ignore[arg-type]
    lines = _read_jsonl_lines(tmp_path)
    assert len(lines) == 2
    assert lines[0]["idempotency_key"] == lines[1]["idempotency_key"]
