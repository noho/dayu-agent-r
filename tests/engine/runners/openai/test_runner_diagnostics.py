"""Runner 诊断日志测试（Phase 1.5）。

覆盖 :class:`~dayu.engine.runners.openai.runner.AsyncOpenAIRunner`
在关键阶段（attempt 起点 / 重试 / 终态错误 / 取消）输出 ``dayu.*``
namespace 下的诊断日志，且不污染 RunnerEvent 流。
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import RunnerEvent, RunnerEventType
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeCancellationToken,
    FakeResponseSpec,
    FakeSession,
)


def _attach_caplog_to_dayu(
    caplog: pytest.LogCaptureFixture,
) -> logging.Logger:
    """把 caplog handler 显式挂到 dayu logger 并返回。"""

    namespace_logger = logging.getLogger("dayu")
    namespace_logger.addHandler(caplog.handler)
    return namespace_logger


async def _never_finishing_readany() -> bytes:
    """模拟永不自然返回的 ``readany``。

    :returns: 不会返回。
    :raises asyncio.CancelledError: task 被取消时由 ``asyncio.sleep`` 抛出。
    """

    await asyncio.sleep(3600.0)
    return b""


async def _readany_raises_runtime_error_on_cancel() -> bytes:
    """模拟 ``readany`` 在取消清理阶段抛出普通异常。

    :returns: 不会返回。
    :raises RuntimeError: task 被取消后抛出。
    """

    try:
        await asyncio.sleep(3600.0)
    except asyncio.CancelledError as exc:
        raise RuntimeError("read cleanup failed") from exc
    return b""


@pytest.mark.asyncio
async def test_attempt_start_diagnostic_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """成功路径应至少输出一条 attempt.start 诊断日志。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"hi"},"finish_reason":"stop"}]}'
            ],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=FakeCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            events: list[RunnerEvent] = []
            async for event in runner.call(
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                events.append(event)
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert any(
        "runner.attempt.start" in r.getMessage() for r in caplog.records
    )
    assert events[-1].type is RunnerEventType.RUNNER_DONE


@pytest.mark.asyncio
async def test_cancelled_diagnostic_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """token 已取消时应输出 runner.cancelled 诊断日志。"""

    token = FakeCancellationToken(cancelled=True, reason="test-cancel")
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"{}"],
        )
    )
    runner = AsyncOpenAIRunner(spec=make_spec(), cancellation_token=token)
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert any(
        "runner.cancelled" in r.getMessage() for r in caplog.records
    )


@pytest.mark.asyncio
async def test_cancel_pending_readany_cancelled_error_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """pending readany 正常响应取消时不写 warning。"""

    task = asyncio.create_task(_never_finishing_readany())
    await asyncio.sleep(0)

    with caplog.at_level(
        logging.WARNING, logger="dayu.engine.runners.openai.runner"
    ):
        await AsyncOpenAIRunner._cancel_pending_readany(task)

    assert task.cancelled()
    assert "runner.pending_readany_cancel_failed" not in caplog.text


@pytest.mark.asyncio
async def test_cancel_pending_readany_exception_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """pending readany 取消清理抛普通异常时记录 warning 与异常类型。"""

    task = asyncio.create_task(_readany_raises_runtime_error_on_cancel())
    await asyncio.sleep(0)

    with caplog.at_level(
        logging.WARNING, logger="dayu.engine.runners.openai.runner"
    ):
        await AsyncOpenAIRunner._cancel_pending_readany(task)

    assert "runner.pending_readany_cancel_failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_terminal_error_logged_at_warning_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """终态 HTTP 错误必须以 WARNING 级别记录 runner.attempt.terminal。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=400,
            headers={"Content-Type": "application/json"},
            body_chunks=[b'{"error":"bad"}'],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(max_retries=0),
        cancellation_token=FakeCancellationToken(),
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    terminal_records = [
        r for r in caplog.records
        if "runner.attempt.terminal" in r.getMessage()
    ]
    assert terminal_records
    assert all(r.levelno >= logging.WARNING for r in terminal_records)


@pytest.mark.asyncio
async def test_runner_logs_use_dayu_namespace_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Runner 日志必须在 ``dayu.*`` namespace，不污染 root。"""

    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body_chunks=[
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"hi"},"finish_reason":"stop"}]}'
            ],
        )
    )
    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=FakeCancellationToken()
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    namespace_logger = _attach_caplog_to_dayu(caplog)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
            async for _event in runner.call(
                messages=msgs, options=make_options(stream=False), tools=[]
            ):
                pass
    finally:
        namespace_logger.removeHandler(caplog.handler)

    runner_records = [
        r for r in caplog.records if r.name.startswith("dayu.")
    ]
    assert runner_records
    for record in caplog.records:
        # 任何 caplog 抓到的日志都应来自 dayu namespace；root 不该被污染。
        assert record.name == "dayu" or record.name.startswith("dayu.")
