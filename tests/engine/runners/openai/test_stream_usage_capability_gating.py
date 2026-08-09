"""``stream_options.include_usage`` capability 门控测试。"""

from __future__ import annotations

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.runners.openai.payload import build_request_payload

from tests.engine.runners.openai._factories import make_options, make_spec


def _msgs() -> list[UserMessage]:
    """构造最小消息序列。"""

    return [UserMessage(role=AgentMessageRole.USER, content="hi")]


def test_stream_true_supports_usage_true_writes_include_usage() -> None:
    """``stream=True`` + ``supports_stream_usage=True`` 写入 ``include_usage=True``。"""

    spec = make_spec(supports_stream_usage=True)
    payload = build_request_payload(
        messages=_msgs(),
        options=make_options(stream=True),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("stream_options") == {"include_usage": True}


def test_stream_true_supports_usage_false_no_stream_options() -> None:
    """``stream=True`` + ``supports_stream_usage=False`` 不写 ``stream_options``。"""

    spec = make_spec(supports_stream_usage=False)
    payload = build_request_payload(
        messages=_msgs(),
        options=make_options(stream=True),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert "stream_options" not in payload


def test_stream_false_no_stream_options() -> None:
    """``stream=False`` 一律不写 ``stream_options``。"""

    spec_true = make_spec(supports_stream_usage=True)
    payload_true = build_request_payload(
        messages=_msgs(),
        options=make_options(stream=False),
        tools=[],
        spec=spec_true,
        structured_output=None,
    )
    assert "stream_options" not in payload_true

    spec_false = make_spec(supports_stream_usage=False)
    payload_false = build_request_payload(
        messages=_msgs(),
        options=make_options(stream=False),
        tools=[],
        spec=spec_false,
        structured_output=None,
    )
    assert "stream_options" not in payload_false
