"""OpenAI runner response 获取取消竞态的资源清理回归测试。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import TracebackType

import aiohttp
import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import RunnerEvent
import dayu.engine.runners.openai.runner as openai_runner
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner
from dayu.runtime.cancellation import WaitCancelled

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_options, make_spec


class _TrackedResponse:
    """记录 response 是否被读取与释放的 fake response。"""

    def __init__(self) -> None:
        """构造 fake response。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.status: int = 200
        self.headers: Mapping[str, str] = {"Content-Type": "application/json"}
        self.release_count: int = 0
        self.read_count: int = 0

    async def read(self) -> bytes:
        """记录正文读取并返回空 JSON。

        :returns: JSON 响应体字节串。
        :raises Exception: 不主动抛出异常。
        """

        self.read_count += 1
        return b"{}"

    async def text(self) -> str:
        """返回文本响应体。

        :returns: JSON 响应体文本。
        :raises Exception: 不主动抛出异常。
        """

        return "{}"

    def release(self) -> None:
        """记录 release 调用次数。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.release_count += 1


class _AcquireResponseContext:
    """立即产出 fake response 的 async context manager。"""

    def __init__(self) -> None:
        """构造 context。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.response: _TrackedResponse | None = None

    async def __aenter__(self) -> aiohttp.ClientResponse:
        """进入 context 并产出 fake response。

        :returns: 类型上模拟 :class:`aiohttp.ClientResponse` 的 fake response。
        :raises Exception: 不主动抛出异常。
        """

        self.response = _TrackedResponse()
        return self.response  # type: ignore[return-value]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出 context。

        :param exc_type: 异常类型。
        :param exc: 异常实例。
        :param tb: traceback。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        return None


class _NeverAcquireResponseContext:
    """永不产出 response，直到测试取消 enter task。"""

    def __init__(self) -> None:
        """构造 context。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.response: _TrackedResponse | None = None

    async def __aenter__(self) -> aiohttp.ClientResponse:
        """等待直到被取消，模拟 acquisition 尚未产出 response。

        :returns: 类型上模拟 :class:`aiohttp.ClientResponse` 的 fake response。
        :raises asyncio.CancelledError: enter task 被取消时透传。
        """

        await asyncio.sleep(10.0)
        self.response = _TrackedResponse()
        return self.response  # type: ignore[return-value]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出 context。

        :param exc_type: 异常类型。
        :param exc: 异常实例。
        :param tb: traceback。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        return None


class _CancelOuterAfterAcquireContext:
    """response 取得后调度取消外层 runner task 的 context。"""

    def __init__(self) -> None:
        """构造 context。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.response: _TrackedResponse | None = None
        self.outer_task: asyncio.Task[aiohttp.ClientResponse] | None = None

    async def __aenter__(self) -> aiohttp.ClientResponse:
        """取得 response 后取消外层 task，并立即返回 response。

        :returns: 类型上模拟 :class:`aiohttp.ClientResponse` 的 fake response。
        :raises AssertionError: 测试未注入外层 task 时抛出。
        """

        if self.outer_task is None:
            raise AssertionError("outer task must be set before __aenter__")
        self.response = _TrackedResponse()
        asyncio.get_running_loop().call_soon(self.outer_task.cancel)
        return self.response  # type: ignore[return-value]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出 context。

        :param exc_type: 异常类型。
        :param exc: 异常实例。
        :param tb: traceback。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        return None


class _RaceSession:
    """返回指定 response context 的 fake session。"""

    def __init__(
        self,
        context: _AcquireResponseContext | _NeverAcquireResponseContext,
    ) -> None:
        """构造 fake session。

        :param context: ``post`` 返回的 response context。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._context: _AcquireResponseContext | _NeverAcquireResponseContext = (
            context
        )
        self.closed: bool = False

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: Mapping[str, str],
    ) -> _AcquireResponseContext | _NeverAcquireResponseContext:
        """返回预置 response context。

        :param url: 请求 URL。
        :param data: 请求体。
        :param headers: 请求头。
        :returns: 预置 response context。
        :raises Exception: 不主动抛出异常。
        """

        return self._context

    async def close(self) -> None:
        """关闭 fake session。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.closed = True


async def _collect_events(runner: AsyncOpenAIRunner) -> list[RunnerEvent]:
    """收集 runner 事件。

    :param runner: 待执行的 runner。
    :returns: runner 发出的事件列表。
    :raises Exception: 透传 runner 执行异常。
    """

    messages = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events: list[RunnerEvent] = []
    async for event in runner.call(messages, make_options(stream=False), []):
        events.append(event)
    return events


async def _cancel_after_response_entered(
    pending: asyncio.Task[aiohttp.ClientResponse],
    *,
    token: CancellationToken,
    timeout_seconds: float | None,
) -> WaitCancelled:
    """模拟 response enter 已完成，但 cancellation 分支赢得 race。

    :param pending: response enter task。
    :param token: 取消 token。
    :param timeout_seconds: timeout 秒数。
    :returns: cancellation 分支结果。
    :raises Exception: 透传 pending 异常。
    """

    await pending
    return WaitCancelled(reason=token.cancel_reason())


async def _cancel_before_response_entered(
    pending: asyncio.Task[aiohttp.ClientResponse],
    *,
    token: CancellationToken,
    timeout_seconds: float | None,
) -> WaitCancelled:
    """模拟 acquisition 尚未完成时 cancellation 先胜出。

    :param pending: response enter task。
    :param token: 取消 token。
    :param timeout_seconds: timeout 秒数。
    :returns: cancellation 分支结果。
    :raises Exception: 不主动抛出异常。
    """

    return WaitCancelled(reason=token.cancel_reason())


@pytest.mark.asyncio
async def test_cancel_after_response_acquired_releases_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """response 已取得且取消胜出时，只 release 一次且不读取正文。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: 无返回值。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    token = ControllableCancellationToken()
    context = _AcquireResponseContext()
    runner = AsyncOpenAIRunner(spec=make_spec(), cancellation_token=token)
    runner._http_client._session = _RaceSession(context)  # type: ignore[attr-defined]

    monkeypatch.setattr(
        openai_runner,
        "_runtime_wait_for_or_cancel",
        _cancel_after_response_entered,
    )

    events = await _collect_events(runner)
    await runner.close()

    assert events == []
    assert context.response is not None
    assert context.response.release_count == 1
    assert context.response.read_count == 0


@pytest.mark.asyncio
async def test_outer_task_cancel_after_response_acquired_propagates_and_releases_once() -> None:
    """外层 task 取消时应透传 ``CancelledError`` 并释放已取得 response。

    :returns: 无返回值。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    context = _CancelOuterAfterAcquireContext()
    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    runner_task = asyncio.create_task(
        runner._enter_response_context_or_cancel(context.__aenter__())
    )
    context.outer_task = runner_task

    with pytest.raises(asyncio.CancelledError):
        await runner_task

    assert context.response is not None
    assert context.response.release_count == 1
    assert context.response.read_count == 0


@pytest.mark.asyncio
async def test_cancel_before_response_acquired_does_not_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """response 尚未取得时取消，不应调用 release。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: 无返回值。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    context = _NeverAcquireResponseContext()
    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    runner._http_client._session = _RaceSession(context)  # type: ignore[attr-defined]

    monkeypatch.setattr(
        openai_runner,
        "_runtime_wait_for_or_cancel",
        _cancel_before_response_entered,
    )

    events = await _collect_events(runner)
    await runner.close()

    assert events == []
    assert context.response is None
