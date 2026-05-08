"""Host P6 RunEventData 序列化注册表行为测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.engine import (
    ContentDeltaData,
    FinalAnswerData,
    FinishReason,
    RunCancelledData,
    RunFailedData,
)
from dayu.host._run_event_serializer import (
    CURRENT_SCHEMA_VERSION,
    deserialize_run_event_data,
    is_known_run_event_type,
    serialize_run_event_data,
)
from dayu.host.contracts import (
    HostRunFailedData,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)


def _utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def test_round_trip_content_delta() -> None:
    """ContentDeltaData JSON round trip。"""

    original = ContentDeltaData(iteration_id="iter-1", delta="hello")
    raw = serialize_run_event_data(
        event_type=RunEventType.RUNNER_CONTENT_DELTA, data=original
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.RUNNER_CONTENT_DELTA, raw=raw
    )
    assert decoded == original


def test_round_trip_final_answer() -> None:
    """FinalAnswerData round trip 保持 finish_reason 枚举。"""

    original = FinalAnswerData(
        content="ok",
        filtered=False,
        degraded=False,
        finish_reason=FinishReason.STOP,
    )
    raw = serialize_run_event_data(
        event_type=RunEventType.FINAL_ANSWER, data=original
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.FINAL_ANSWER, raw=raw
    )
    assert decoded == original


def test_run_failed_engine_vs_host_variants_distinguished() -> None:
    """RUN_FAILED 同时支持 Engine 和 Host 变体，靠 exception_type 区分。"""

    engine = RunFailedData(
        error_code="model_unavailable", message="m", recoverable=False
    )
    raw_engine = serialize_run_event_data(
        event_type=RunEventType.RUN_FAILED, data=engine
    )
    decoded_engine = deserialize_run_event_data(
        event_type=RunEventType.RUN_FAILED, raw=raw_engine
    )
    assert isinstance(decoded_engine, RunFailedData)
    assert decoded_engine == engine

    host = HostRunFailedData(
        error_code="worker_internal_error",
        message="boom",
        recoverable=False,
        exception_type="RuntimeError",
    )
    raw_host = serialize_run_event_data(
        event_type=RunEventType.RUN_FAILED, data=host
    )
    decoded_host = deserialize_run_event_data(
        event_type=RunEventType.RUN_FAILED, raw=raw_host
    )
    assert isinstance(decoded_host, HostRunFailedData)
    assert decoded_host == host


def test_run_cancelled_round_trip_preserves_timestamps() -> None:
    """RunCancelledData ISO 时间戳 round trip。"""

    now = _utc()
    original = RunCancelledData(
        reason="user_cancel",
        requested_at=now,
        accepted_at=now,
        finished_at=now,
    )
    raw = serialize_run_event_data(
        event_type=RunEventType.RUN_CANCELLED, data=original
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.RUN_CANCELLED, raw=raw
    )
    assert isinstance(decoded, RunCancelledData)
    assert decoded.requested_at == now


def test_user_input_accepted_round_trip() -> None:
    """UserInputAcceptedData scope 枚举 round trip。"""

    original = UserInputAcceptedData(
        turn_id="t1", content="hi", scope=UserInputScope.SESSION
    )
    raw = serialize_run_event_data(
        event_type=RunEventType.USER_INPUT_ACCEPTED, data=original
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.USER_INPUT_ACCEPTED, raw=raw
    )
    assert decoded == original


def test_serialize_rejects_type_data_mismatch() -> None:
    """event_type 与 data 不匹配必须 fail-fast。"""

    with pytest.raises(ValueError):
        serialize_run_event_data(
            event_type=RunEventType.FINAL_ANSWER,
            data=ContentDeltaData(iteration_id="x", delta="y"),
        )


def test_deserialize_rejects_unsupported_schema_version() -> None:
    """schema_version 不匹配必须 fail-fast。"""

    raw = (
        '{"schema_version": 999, "type_name": "final_answer::FinalAnswerData",'
        ' "fields": {}}'
    )
    with pytest.raises(ValueError):
        deserialize_run_event_data(
            event_type=RunEventType.FINAL_ANSWER, raw=raw
        )


def test_deserialize_rejects_type_name_mismatch() -> None:
    """type_name 与 event_type 不匹配必须 fail-fast。"""

    raw = (
        '{"schema_version": 1, "type_name": "wrong::FinalAnswerData",'
        ' "fields": {}}'
    )
    with pytest.raises(ValueError):
        deserialize_run_event_data(
            event_type=RunEventType.FINAL_ANSWER, raw=raw
        )


def test_schema_version_is_current() -> None:
    """schema_version 注册表常量与序列化输出一致。"""

    raw = serialize_run_event_data(
        event_type=RunEventType.RUNNER_CONTENT_DELTA,
        data=ContentDeltaData(iteration_id="i", delta="d"),
    )
    assert f'"schema_version": {CURRENT_SCHEMA_VERSION}' in raw


def test_is_known_run_event_type_covers_canonical_types() -> None:
    """常见 canonical 类型在注册表内。"""

    assert is_known_run_event_type(RunEventType.FINAL_ANSWER)
    assert is_known_run_event_type(RunEventType.RUNNER_CONTENT_DELTA)
    assert is_known_run_event_type(RunEventType.USER_INPUT_ACCEPTED)
