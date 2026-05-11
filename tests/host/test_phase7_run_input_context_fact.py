"""P7 S2 RunInputContextFactBuilder 测试。

覆盖：

- builder 输出 ``RunInputContextSnapshotBuiltData`` 字段一致。
- raw payload blob id / sha256 / byte size 跨 replay 稳定。
- raw payload JSON 由 build result 单独返回，不进入 EventLog fact data。
- 当前用户事件类型不匹配时抛异常。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine import (
    AgentMessageRole,
    AssistantMessage,
    AssistantToolCall,
    SystemMessage,
    UserMessage,
)
from dayu.host._run_input_builder import RunInputBuildTrace
from dayu.host._run_input_context_fact import RunInputContextFactBuilder
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunInput,
    UserInputAcceptedData,
    UserInputScope,
)


def _user_event(content: str = "你好", run_id: str = "r1") -> RunEvent:
    """构造 USER_INPUT_ACCEPTED 事件样例。

    :param content: 用户文本。
    :param run_id: Run id。
    :returns: RunEvent 实例。
    :raises Exception: 不主动抛出异常。
    """

    return RunEvent(
        run_id=run_id,
        session_id="s1",
        cursor=RunEventCursor(sequence=3),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.USER_INPUT_ACCEPTED,
        occurred_at=datetime.now(tz=timezone.utc),
        data=UserInputAcceptedData(
            turn_id=run_id,
            content=content,
            scope=UserInputScope.SESSION,
        ),
        source_engine_event_id=None,
    )


def _run_input() -> RunInput:
    """构造 RunInput 样例。

    :returns: RunInput 实例。
    :raises Exception: 不主动抛出异常。
    """

    return RunInput(
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content="你是助手"),
            UserMessage(role=AgentMessageRole.USER, content="你好"),
        )
    )


def _tool_schema() -> ToolSchema:
    """构造 ToolSchema 样例。

    :returns: ToolSchema 实例。
    :raises Exception: 不主动抛出异常。
    """

    return ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="echo",
            description="echo input",
            parameters=ToolParametersSchema(
                type="object",
                properties={"text": {"type": "string"}},
                required=("text",),
                additional_properties=None,
            ),
        ),
    )


def _trace() -> RunInputBuildTrace:
    """构造 RunInputBuildTrace 样例。

    :returns: RunInputBuildTrace 实例。
    :raises Exception: 不主动抛出异常。
    """

    return RunInputBuildTrace(
        session_id="s1",
        run_id="r1",
        items=(),
        total_char_size=10,
        total_token_estimate=8,
    )


def test_builder_outputs_consistent_summary() -> None:
    """builder 把 RunInput / event 派生为 snapshot data。"""

    builder = RunInputContextFactBuilder()
    built = builder.build(
        run_input=_run_input(),
        build_trace=_trace(),
        current_user_event=_user_event(),
        tool_schemas=(_tool_schema(),),
        attempt_index=0,
        iteration_index=0,
        iteration_id="r1-attempt-00",
    )
    data = built.data
    assert data.iteration_id == "r1-attempt-00"
    assert data.attempt_index == 0
    assert data.iteration_index == 0
    assert data.current_user_excerpt == "你好"
    assert len(data.message_summaries) == 2
    roles = tuple(m.role for m in data.message_summaries)
    assert roles == ("system", "user")
    assert data.message_summaries[0].source_kind == "caller_system"
    assert data.message_summaries[1].source_kind == "current_user"
    assert len(data.tool_schema_summaries) == 1
    assert data.tool_schema_summaries[0].name == "echo"
    assert data.context_meta.message_count == 2
    assert data.context_meta.role_sequence == ("system", "user")
    assert data.context_meta.current_user_run_id == "r1"
    # raw payload 不进入 EventLog data，但 build result 必须保留可写入
    # side-store 的 JSON。
    parsed = json.loads(built.raw_payloads.input_messages_json)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert data.raw_input_messages_byte_size == len(
        built.raw_payloads.input_messages_json.encode("utf-8")
    )


def test_raw_input_messages_scrub_assistant_tool_call_credentials() -> None:
    """RunInput raw payload 中 assistant tool call 参数清洗显式凭证。"""

    run_input = RunInput(
        messages=(
            AssistantMessage(
                role=AgentMessageRole.ASSISTANT,
                content=None,
                reasoning_content=None,
                tool_calls=(
                    AssistantToolCall(
                        id="tc-1",
                        name="secret_tool",
                        arguments={
                            "api_key": "sk-api",
                            "password": "pw",
                            "client_secret": "client-secret",
                            "Authorization": "Bearer secret",
                            "access_token": "access-secret",
                            "cursor": "cursor-public",
                            "scope_token": "scope-public",
                            "token": "ordinary-token",
                        },
                        provider_state=None,
                    ),
                ),
            ),
        )
    )
    built = RunInputContextFactBuilder().build(
        run_input=run_input,
        build_trace=_trace(),
        current_user_event=_user_event(),
        tool_schemas=(),
        attempt_index=0,
        iteration_index=0,
        iteration_id="r1-attempt-00",
    )

    raw = json.loads(built.raw_payloads.input_messages_json)
    assert isinstance(raw, list)
    first = raw[0]
    assert isinstance(first, dict)
    tool_calls = first["tool_calls"]
    assert isinstance(tool_calls, list)
    call = tool_calls[0]
    assert isinstance(call, dict)
    arguments = call["arguments"]
    assert isinstance(arguments, dict)
    assert arguments["api_key"] == "***"
    assert arguments["password"] == "***"
    assert arguments["client_secret"] == "***"
    assert arguments["Authorization"] == "***"
    assert arguments["access_token"] == "***"
    assert arguments["cursor"] == "cursor-public"
    assert arguments["scope_token"] == "scope-public"
    assert arguments["token"] == "ordinary-token"


def test_builder_blob_id_stable_across_calls() -> None:
    """同样 run_id / iteration_id / role 的 blob_id 跨调用稳定。"""

    builder = RunInputContextFactBuilder()
    a = builder.build(
        run_input=_run_input(),
        build_trace=_trace(),
        current_user_event=_user_event(),
        tool_schemas=(_tool_schema(),),
        attempt_index=0,
        iteration_index=0,
        iteration_id="r1-attempt-00",
    )
    b = builder.build(
        run_input=_run_input(),
        build_trace=_trace(),
        current_user_event=_user_event(),
        tool_schemas=(_tool_schema(),),
        attempt_index=0,
        iteration_index=0,
        iteration_id="r1-attempt-00",
    )
    assert a.data.raw_input_messages_blob_id == b.data.raw_input_messages_blob_id
    assert a.data.raw_tool_schemas_blob_id == b.data.raw_tool_schemas_blob_id
    assert a.data.raw_input_messages_blob_id != a.data.raw_tool_schemas_blob_id
    assert a.data.raw_input_messages_sha256 == b.data.raw_input_messages_sha256
    assert a.raw_payloads.input_messages_json == b.raw_payloads.input_messages_json


def test_builder_rejects_non_user_input_event() -> None:
    """当前用户事件不是 USER_INPUT_ACCEPTED 时抛 ValueError。"""

    bad = RunEvent(
        run_id="r1",
        session_id="s1",
        cursor=RunEventCursor(sequence=0),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=datetime.now(tz=timezone.utc),
        data=UserInputAcceptedData(
            turn_id="r1", content="x", scope=UserInputScope.SESSION
        ),
        source_engine_event_id=None,
    )
    builder = RunInputContextFactBuilder()
    with pytest.raises(ValueError):
        builder.build(
            run_input=_run_input(),
            build_trace=_trace(),
            current_user_event=bad,
            tool_schemas=(),
            attempt_index=0,
            iteration_index=0,
            iteration_id="r1-attempt-00",
        )


def test_builder_independent_of_harness_lru() -> None:
    """builder 是 frozen dataclass，不维护任何状态。"""

    builder = RunInputContextFactBuilder()
    # 多次调用不破坏 builder 字段。
    for _ in range(3):
        builder.build(
            run_input=_run_input(),
            build_trace=_trace(),
            current_user_event=_user_event(),
            tool_schemas=(),
            attempt_index=0,
            iteration_index=0,
            iteration_id="r1-attempt-00",
        )
    assert builder.excerpt_char_limit == 256
