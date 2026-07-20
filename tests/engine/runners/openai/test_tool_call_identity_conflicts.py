"""OpenAI 流式 tool-call identity binding 冲突测试。"""

from __future__ import annotations

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEventType,
    RunnerProtocolErrorData,
)
from dayu.engine.runners.openai.tool_call_aggregator import ToolCallAggregator

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.parametrize("invalid_index", (-1, -2, True, 1.5, "0"))
def test_explicit_invalid_native_index_is_fatal(
    invalid_index: JsonValue,
) -> None:
    """显式非法 native index 必须 fatal 且不能进入 synthetic path。

    :param invalid_index: 非 bool、非负 int 约束之外的 provider 值。
    :returns: 无返回值。
    :raises AssertionError: 非法值被接受时由 pytest 抛出。
    """

    aggregator = ToolCallAggregator(provider_request_id="req-invalid-index")
    resolved = aggregator.feed(
        {
            "index": invalid_index,
            "id": "call-invalid",
            "function": {"name": "lookup", "arguments": "{}"},
        },
        position=0,
    )

    result = aggregator.finalize()
    assert resolved is None
    assert result.tool_calls == ()
    assert len(result.fatal_errors) == 1
    assert result.fatal_errors[0].error_code == "tool_call_invalid_index"


def test_missing_index_with_id_and_same_identity_continuations_succeed() -> None:
    """缺 index 的 id 可获 synthetic identity，相同 identity 分片可续接。"""

    aggregator = ToolCallAggregator(provider_request_id=None)
    synthetic = aggregator.feed(
        {
            "id": "call-synthetic",
            "function": {"name": "look", "arguments": "{\"a\":"},
        },
        position=0,
    )
    continued = aggregator.feed(
        {
            "id": "call-synthetic",
            "function": {"name": "up", "arguments": "1}"},
        },
        position=0,
    )

    result = aggregator.finalize()
    assert synthetic == continued == -1
    assert result.fatal_errors == ()
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "lookup"
    assert result.tool_calls[0].arguments == {"a": 1}


def test_same_id_and_same_native_index_continuations_succeed() -> None:
    """相同 id 与相同 native index 的正常分片必须稳定聚合。"""

    aggregator = ToolCallAggregator(provider_request_id=None)
    first = aggregator.feed(
        {
            "index": 0,
            "id": "call-native",
            "function": {"name": "look", "arguments": "{\"a\":"},
        },
        position=0,
    )
    second = aggregator.feed(
        {
            "index": 0,
            "id": "call-native",
            "function": {"name": "up", "arguments": "1}"},
        },
        position=0,
    )

    result = aggregator.finalize()
    assert first == second == 0
    assert result.fatal_errors == ()
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "lookup"
    assert result.tool_calls[0].arguments == {"a": 1}


def test_synthetic_identity_migrates_to_empty_native_target() -> None:
    """synthetic id 首次声明未占用 native target 时允许无损迁移。"""

    aggregator = ToolCallAggregator(provider_request_id=None)
    first = aggregator.feed(
        {
            "id": "call-a",
            "function": {"name": "lookup", "arguments": "{\"a\":"},
        },
        position=0,
    )
    migrated = aggregator.feed(
        {
            "index": 2,
            "id": "call-a",
            "function": {"arguments": "1}"},
        },
        position=0,
    )

    result = aggregator.finalize()
    assert first == -1
    assert migrated == 2
    assert result.fatal_errors == ()
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].arguments == {"a": 1}


@pytest.mark.parametrize(
    "second_delta",
    (
        {
            "index": 0,
            "id": "call-b",
            "function": {"name": "delete", "arguments": "{}"},
        },
        {
            "index": 1,
            "id": "call-a",
            "function": {"name": "delete", "arguments": "{}"},
        },
    ),
)
def test_native_index_and_id_conflicts_are_fatal_without_fragment_merge(
    second_delta: dict[str, JsonValue],
) -> None:
    """same-index/two-id 与 same-id/two-index 均不得拼接 partial。

    :param second_delta: 与首条 identity 冲突的 provider delta。
    :returns: 无返回值。
    :raises AssertionError: 冲突被合并时由 pytest 抛出。
    """

    aggregator = ToolCallAggregator(provider_request_id=None)
    aggregator.feed(
        {
            "index": 0,
            "id": "call-a",
            "function": {"name": "lookup", "arguments": "{}"},
        },
        position=0,
    )
    resolved = aggregator.feed(second_delta, position=0)

    result = aggregator.finalize()
    assert resolved is None
    assert [error.error_code for error in result.fatal_errors] == [
        "tool_call_identity_conflict"
    ]
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "lookup"
    assert all(call.name != "lookupdelete" for call in result.tool_calls)


def test_synthetic_identity_cannot_migrate_to_occupied_native_target() -> None:
    """synthetic source 迁移到已占用 native target 时必须 fatal。"""

    aggregator = ToolCallAggregator(provider_request_id=None)
    aggregator.feed(
        {
            "index": 0,
            "id": "call-a",
            "function": {"name": "lookup", "arguments": "{}"},
        },
        position=0,
    )
    aggregator.feed(
        {
            "id": "call-b",
            "function": {"name": "delete", "arguments": "{}"},
        },
        position=1,
    )
    resolved = aggregator.feed(
        {
            "index": 0,
            "id": "call-b",
            "function": {"name": "ignored", "arguments": "{}"},
            "extra_content": {"google": {"thought_signature": "ignored"}},
        },
        position=0,
    )

    result = aggregator.finalize()
    assert resolved is None
    assert [error.error_code for error in result.fatal_errors] == [
        "tool_call_identity_conflict"
    ]
    assert {call.name for call in result.tool_calls} == {"lookup", "delete"}
    assert all(call.provider_state is None for call in result.tool_calls)


@pytest.mark.parametrize(
    "conflicting_delta",
    (
        {"index": 1, "id": "call-a", "function": {"name": "ignored"}},
        {"index": 0, "id": "call-b", "function": {"name": "ignored"}},
    ),
)
def test_position_continuation_does_not_bypass_identity_conflicts(
    conflicting_delta: dict[str, JsonValue],
) -> None:
    """position continuation 后仍须执行 id/index 统一冲突校验。

    :param conflicting_delta: same-id/two-index 或 same-index/two-id delta。
    :returns: 无返回值。
    :raises AssertionError: position table 绕过校验时由 pytest 抛出。
    """

    aggregator = ToolCallAggregator(provider_request_id=None)
    aggregator.feed(
        {
            "index": 0,
            "id": "call-a",
            "function": {"name": "lookup", "arguments": "{\"a\":"},
        },
        position=0,
    )
    continued = aggregator.feed(
        {"function": {"arguments": "1}"}},
        position=0,
    )
    conflicted = aggregator.feed(conflicting_delta, position=0)

    result = aggregator.finalize()
    assert continued == 0
    assert conflicted is None
    assert [error.error_code for error in result.fatal_errors] == [
        "tool_call_identity_conflict"
    ]
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].arguments == {"a": 1}


@pytest.mark.asyncio
async def test_position_routed_conflict_fails_closed_without_merge() -> None:
    """position 归入 B 后，B 冲突声明 A 的 native target 必须失败收口。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":['
            b'{"index":0,"id":"call-a","function":'
            b'{"name":"lookup","arguments":"{}"}},'
            b'{"id":"call-b","function":'
            b'{"name":"delete","arguments":"{\\"target\\":"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":['
            b'{"index":0,"id":"call-a","function":{}},'
            b'{"function":{"arguments":"\\"x\\"}"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":['
            b'{"index":0,"id":"call-b","function":'
            b'{"name":"ignored","arguments":"{}"},'
            b'"extra_content":{"google":{"thought_signature":"bad"}}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    events = await parse_sse(chunks)
    assert RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED not in {
        event.type for event in events
    }
    errors = [
        event.data
        for event in events
        if event.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    ]
    assert len(errors) == 1
    error = errors[0]
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "tool_call_identity_conflict"
    assert {summary.name_fragment for summary in error.partial_tool_calls} == {
        "lookup",
        "delete",
    }
    assert all(
        summary.name_fragment != "lookupdelete"
        for summary in error.partial_tool_calls
    )
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
