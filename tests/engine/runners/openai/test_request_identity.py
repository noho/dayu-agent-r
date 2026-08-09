"""OpenAI-compatible request identity header 映射测试。

本模块只覆盖 RunnerSpec 显式 policy 到 outbound
``X-Client-Request-Id`` 的映射，不测试 Host projection / Tool Trace 行为。
"""

from __future__ import annotations

import asyncio

import pytest

from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import RunnerEvent
from dayu.engine.contracts.runner_identity import (
    RunnerRequestIdentity,
    build_runner_request_identity,
)
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeResponseSpec,
    FakeSession,
)


def _identity() -> RunnerRequestIdentity:
    """构造稳定的测试请求身份。

    :returns: 单次逻辑 Runner 调用身份。
    :raises ValueError: 身份字段不满足契约时抛出。
    """

    return build_runner_request_identity(
        run_id="run-request-identity",
        attempt_id="attempt-request-identity",
        execution_id="execution-request-identity",
        iteration_id="iteration-request-identity",
        iteration_index=0,
        runner_call_index=1,
    )


def _runner(
    *,
    policy: ClientCorrelationPolicy,
    headers: dict[str, str] | None = None,
    max_retries: int = 0,
) -> AsyncOpenAIRunner:
    """构造安装了指定 client correlation policy 的 Runner。

    :param policy: 客户端关联 id outbound 映射策略。
    :param headers: 静态 RunnerSpec headers。
    :param max_retries: 最大 transport retry 次数。
    :returns: OpenAI-compatible Runner。
    :raises ValueError: RunnerSpec 字段不满足契约时抛出。
    """

    return AsyncOpenAIRunner(
        spec=make_spec(
            headers=headers,
            client_correlation_policy=policy,
            max_retries=max_retries,
        ),
        cancellation_token=ControllableCancellationToken(),
    )


def _install_session(
    runner: AsyncOpenAIRunner,
    session: FakeSession,
) -> None:
    """把 fake HTTP session 安装到 Runner。

    :param runner: 待安装 session 的 Runner。
    :param session: fake HTTP session。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    runner._http_client._session = session  # type: ignore[attr-defined]


def _enqueue_http_error(session: FakeSession, *, status: int = 400) -> None:
    """排队一个非流式 HTTP 错误响应。

    :param session: fake HTTP session。
    :param status: HTTP 状态码。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    session.enqueue_response(
        FakeResponseSpec(
            status=status,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"error"],
        )
    )


async def _collect(
    runner: AsyncOpenAIRunner,
    *,
    request_identity: RunnerRequestIdentity | None,
) -> list[RunnerEvent]:
    """执行一次 Runner call 并收集事件。

    :param runner: 待执行的 Runner。
    :param request_identity: 传给 Runner 的请求身份。
    :returns: RunnerEvent 列表。
    :raises Exception: 透传 Runner 执行异常。
    """

    events: list[RunnerEvent] = []
    async for event in runner.call(
        structured_output=None,
        messages=[UserMessage(role=AgentMessageRole.USER, content="hi")],
        options=make_options(stream=False),
        tools=[],
        request_identity=request_identity,
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_policy_enabled_sends_x_client_request_id() -> None:
    """policy 开启且 request identity 存在时发送客户端关联 header。"""

    identity = _identity()
    runner = _runner(policy=ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID)
    session = FakeSession()
    _enqueue_http_error(session)
    _install_session(runner, session)

    await _collect(runner, request_identity=identity)

    assert session.calls[0][2]["X-Client-Request-Id"] == (
        identity.client_correlation_id
    )


@pytest.mark.asyncio
async def test_policy_disabled_does_not_send_x_client_request_id() -> None:
    """policy disabled 时即使有 request identity 也不发送客户端关联 header。"""

    runner = _runner(policy=ClientCorrelationPolicy.DISABLED)
    session = FakeSession()
    _enqueue_http_error(session)
    _install_session(runner, session)

    await _collect(runner, request_identity=_identity())

    assert "X-Client-Request-Id" not in session.calls[0][2]


@pytest.mark.asyncio
async def test_policy_disabled_without_identity_does_not_send_header() -> None:
    """policy disabled 且 request identity 缺失时不发送客户端关联 header。

    :returns: 无返回值。
    :raises Exception: Runner 执行失败时透传异常。
    """

    runner = _runner(policy=ClientCorrelationPolicy.DISABLED)
    session = FakeSession()
    _enqueue_http_error(session)
    _install_session(runner, session)

    await _collect(runner, request_identity=None)

    assert "X-Client-Request-Id" not in session.calls[0][2]


@pytest.mark.asyncio
async def test_policy_enabled_without_identity_does_not_send_header() -> None:
    """policy 开启但 request identity 缺失时不发送客户端关联 header。"""

    runner = _runner(policy=ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID)
    session = FakeSession()
    _enqueue_http_error(session)
    _install_session(runner, session)

    await _collect(runner, request_identity=None)

    assert "X-Client-Request-Id" not in session.calls[0][2]


def test_policy_enabled_rejects_static_case_insensitive_header() -> None:
    """policy 开启时 RunnerSpec 边界拒绝静态客户端关联 header。"""

    with pytest.raises(ValueError, match="X-Client-Request-Id"):
        _runner(
            policy=ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID,
            headers={"x-client-request-id": "static-value"},
        )


@pytest.mark.asyncio
async def test_transport_retry_reuses_same_request_identity_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """transport retry 复用同一个 request identity 与 header 值。"""

    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        """把 retry sleep 压缩为零等待。

        :param delay: 原 sleep 秒数。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        del delay
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    identity = _identity()
    runner = _runner(
        policy=ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID,
        max_retries=1,
    )
    session = FakeSession()
    _enqueue_http_error(session, status=500)
    _enqueue_http_error(session, status=400)
    _install_session(runner, session)

    await _collect(runner, request_identity=identity)

    first_headers = session.calls[0][2]
    second_headers = session.calls[1][2]
    assert first_headers["X-Client-Request-Id"] == identity.client_correlation_id
    assert second_headers["X-Client-Request-Id"] == identity.client_correlation_id
    assert first_headers["X-Client-Request-Id"] == second_headers[
        "X-Client-Request-Id"
    ]
