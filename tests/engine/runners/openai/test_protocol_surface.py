"""协议表面测试：Runner 实现是否严格满足 :class:`AsyncRunner` Protocol。"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.structured_output import (
    JsonSchemaStructuredOutputRequest,
    StructuredOutputCapability,
)
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeResponseSpec,
    FakeSession,
)


def test_runner_isinstance_async_runner_protocol() -> None:
    """``AsyncOpenAIRunner`` 应通过 ``AsyncRunner`` 协议运行时检查。"""

    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    assert isinstance(runner, AsyncRunner)


def test_call_signature_no_kwargs() -> None:
    """``call`` 不能接受 ``**kwargs`` / 其它任意 payload 入口。"""

    sig = inspect.signature(AsyncOpenAIRunner.call)
    assert all(
        p.kind is not inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    ), f"call() must not accept **kwargs: {sig}"
    assert tuple(sig.parameters.keys()) == (
        "self",
        "messages",
        "options",
        "tools",
        "structured_output",
        "request_identity",
    )
    assert (
        sig.parameters["structured_output"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert sig.parameters["structured_output"].default is inspect.Parameter.empty
    assert (
        sig.parameters["request_identity"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert sig.parameters["request_identity"].default is None


@pytest.mark.asyncio
async def test_provider_rejection_does_not_downgrade_or_retry_schema_mode() -> None:
    """Provider 拒绝 JSON Schema 后不得降级或再次发送较弱 mode。"""

    runner = AsyncOpenAIRunner(
        spec=make_spec(
            structured_output_capability=StructuredOutputCapability.JSON_SCHEMA,
            max_retries=3,
        ),
        cancellation_token=ControllableCancellationToken(),
    )
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=400,
            headers={"Content-Type": "application/json"},
            body_chunks=[b'{"error":{"message":"unsupported response format"}}'],
        )
    )
    runner._http_client._session = session  # type: ignore[attr-defined]
    schema: Mapping[str, JsonValue] = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    events = [
        event
        async for event in runner.call(
            messages=[
                UserMessage(role=AgentMessageRole.USER, content="answer")
            ],
            options=make_options(stream=False),
            tools=[],
            structured_output=JsonSchemaStructuredOutputRequest(
                name="owner_schema",
                schema=schema,
                strict=True,
            ),
            request_identity=None,
        )
    ]
    await runner.close()

    assert events
    assert len(session.calls) == 1
    outbound = cast(
        Mapping[str, JsonValue],
        json.loads(session.calls[0][1].decode("utf-8")),
    )
    assert outbound["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "owner_schema",
            "strict": True,
            "schema": schema,
        },
    }


def test_is_supports_tool_calling_returns_spec_value() -> None:
    """``is_supports_tool_calling`` 应直接返回 spec 值。"""

    runner_true = AsyncOpenAIRunner(
        spec=make_spec(supports_tool_calling=True),
        cancellation_token=ControllableCancellationToken(),
    )
    runner_false = AsyncOpenAIRunner(
        spec=make_spec(supports_tool_calling=False),
        cancellation_token=ControllableCancellationToken(),
    )
    assert runner_true.is_supports_tool_calling() is True
    assert runner_false.is_supports_tool_calling() is False


def test_close_is_async() -> None:
    """``close`` 必须是 async 方法。"""

    assert inspect.iscoroutinefunction(AsyncOpenAIRunner.close)


def test_no_set_tools_method() -> None:
    """OLD ``set_tools`` 入口必须不存在。"""

    assert not hasattr(AsyncOpenAIRunner, "set_tools")
