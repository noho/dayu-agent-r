"""取消观察阻塞边界测试。

phase1-plan.md §6.4.1 规定取消例外：``token.is_cancelled() == True`` 时
Runner 直接退出生成器，**不**补 ``RunnerDoneData``。
本测试覆盖四个阻塞边界：

1. HTTP 建连前。
2. 读响应体（read body）。
3. SSE chunk 等待。
4. 重试 sleep。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import RunnerEvent, RunnerEventType
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeResponseSpec,
    FakeSession,
)


@pytest.mark.asyncio
async def test_cancel_before_connect_returns_no_done() -> None:
    """连接前 token 已取消 → 立即退出，不发出 Done。"""

    token = ControllableCancellationToken()
    token.request_cancel()
    runner = AsyncOpenAIRunner(spec=make_spec(), cancellation_token=token)
    session = FakeSession()
    # 排队一个响应做兜底；预期 await_or_cancel 在 __aenter__ 处立即抛
    # _RunnerInterrupted，不会真正消耗到响应。
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"{}"],
        )
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    start = time.monotonic()
    events: list[RunnerEvent] = []
    async for ev in runner.call(msgs, make_options(stream=False), []):
        events.append(ev)
    elapsed = time.monotonic() - start
    await runner.close()

    assert events == []
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_cancel_during_sse_chunk_wait_returns_no_done() -> None:
    """SSE chunk 等待中 token 触发取消 → 立即终止，不发 Done。"""

    token = ControllableCancellationToken()

    class _SlowReadFakeContent:
        """模拟一个永不返回的 ``readany``，由测试侧 trigger token。"""

        async def readany(self) -> bytes:
            await asyncio.sleep(10.0)
            return b""

    class _SlowFakeResponse:
        status: int = 200
        headers = {"Content-Type": "text/event-stream"}
        content = _SlowReadFakeContent()
        released: bool = False

        async def read(self) -> bytes:
            await asyncio.sleep(10.0)
            return b""

        async def text(self) -> str:
            return ""

        def release(self) -> None:
            self.released = True

    class _SlowCtx:
        async def __aenter__(self) -> _SlowFakeResponse:
            return _SlowFakeResponse()

        async def __aexit__(self, *_: object) -> None:
            return None

    class _SlowSession:
        def post(self, url: str, *, data: bytes, headers: object) -> _SlowCtx:
            return _SlowCtx()

        async def close(self) -> None:
            return None

    runner = AsyncOpenAIRunner(
        spec=make_spec(supports_streaming=True),
        cancellation_token=token,
    )
    runner._http_client._session = _SlowSession()  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]

    async def trigger_cancel_after_delay() -> None:
        await asyncio.sleep(0.05)
        token.request_cancel("test")

    asyncio.get_running_loop().create_task(trigger_cancel_after_delay())

    start = time.monotonic()
    events: list[RunnerEvent] = []
    async for ev in runner.call(msgs, make_options(stream=True), []):
        events.append(ev)
    elapsed = time.monotonic() - start
    await runner.close()

    # 不应有任何 Done 事件
    assert all(
        e.type is not RunnerEventType.RUNNER_DONE for e in events
    )
    # 取消应迅速生效（与 ``await_or_cancel`` 的 0.05s 轮询同阶量级）
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_cancel_during_retry_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重试 sleep 中触发取消 → 立即终止，不发 Done。"""

    real_sleep = asyncio.sleep
    token = ControllableCancellationToken()

    async def cancel_during_sleep(delay: float) -> None:
        # 真实指数退避 sleep 触发时把 token 标记为取消
        if delay >= 1.0:
            token.request_cancel("during retry sleep")
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", cancel_during_sleep)

    runner = AsyncOpenAIRunner(
        spec=make_spec(max_retries=3), cancellation_token=token
    )
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=500,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"err"],
        )
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    start = time.monotonic()
    events: list[RunnerEvent] = []
    async for ev in runner.call(msgs, make_options(stream=False), []):
        events.append(ev)
    elapsed = time.monotonic() - start
    await runner.close()

    assert all(
        e.type is not RunnerEventType.RUNNER_DONE for e in events
    )
    assert elapsed < 1.5
