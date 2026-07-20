"""协议表面测试：Runner 实现是否严格满足 :class:`AsyncRunner` Protocol。"""

from __future__ import annotations

import inspect

from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_spec


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
        "request_identity",
    )
    assert (
        sig.parameters["request_identity"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert sig.parameters["request_identity"].default is None


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
