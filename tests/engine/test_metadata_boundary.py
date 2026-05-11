"""metadata / 显式契约边界测试。

通过反射列举 EngineEvent / RunnerEvent 各 data dataclass 字段，断言显式
契约事实（usage 拆分字段、provider_request_id、raw_payload、error_code、
finish_reason 等）直接出现在对应 data dataclass 中，而非塞入开放
metadata。
"""

from __future__ import annotations

import dataclasses

from dayu.engine.contracts.engine_events import (
    ProviderProtocolErrorData,
    RunnerUsageData,
)
from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerProtocolErrorData,
    RunnerUsageRecordedData,
)


def _field_names(cls: type) -> set[str]:
    """返回 dataclass 字段名集合。"""

    return {f.name for f in dataclasses.fields(cls)}


def test_runner_usage_data_uses_split_token_fields() -> None:
    """Engine 侧用量提升事件必须使用拆分字段，不允许整 dict。"""

    fields = _field_names(RunnerUsageData)
    assert {"prompt_tokens", "completion_tokens", "total_tokens"}.issubset(fields)


def test_runner_usage_recorded_data_uses_split_token_fields() -> None:
    """Runner 侧用量事件必须使用拆分字段。"""

    fields = _field_names(RunnerUsageRecordedData)
    assert {"prompt_tokens", "completion_tokens", "total_tokens"} == fields


def test_provider_protocol_error_engine_data_has_explicit_fields() -> None:
    """provider 协议错误事件 data 必须显式承载契约字段。"""

    fields = _field_names(ProviderProtocolErrorData)
    assert {
        "iteration_id",
        "error_code",
        "message",
        "partial_tool_calls",
        "provider_request_id",
        "raw_payload",
    } == fields


def test_provider_protocol_error_runner_data_has_explicit_fields() -> None:
    """Runner 侧 provider 协议错误 data 必须显式承载契约字段。"""

    fields = _field_names(RunnerProtocolErrorData)
    assert {
        "error_code",
        "message",
        "partial_tool_calls",
        "provider_request_id",
        "raw_payload",
    } == fields


def test_partial_tool_call_summary_excludes_raw_arguments() -> None:
    """partial tool call 摘要必须只暴露有界诊断字段。

    参数：无。
    返回值：无。
    异常：断言失败时由 pytest 抛出 ``AssertionError``。
    """

    fields = _field_names(PartialToolCallSummary)
    assert {
        "tool_call_index",
        "tool_call_id",
        "name_fragment",
        "arguments_byte_size",
        "arguments_sha256",
    } == fields
    assert "arguments" not in fields


def test_runner_content_completed_data_has_finish_reason() -> None:
    """正文完成事件必须显式承载 ``finish_reason``。"""

    fields = _field_names(RunnerContentCompletedData)
    assert "finish_reason" in fields
