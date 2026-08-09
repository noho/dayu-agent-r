"""HTTP 1xx / 3xx 非常规状态归类测试。

确保 runner 不再把 ``status >= 400`` 之外的非 200 状态当作成功响应
透给 SSE / 非流式 parser，而是统一归为
:attr:`RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS` + :class:`RunnerDoneData(ERROR)`。
"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
)
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_options, make_spec
from tests.engine.runners.openai._fakes import (
    FakeResponseSpec,
    FakeSession,
)


def _install_session(
    runner: AsyncOpenAIRunner, session: FakeSession
) -> None:
    """把 fake session 安装到 runner.HTTPClient。"""

    client = runner._http_client  # type: ignore[attr-defined]
    client._session = session  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", [199, 300, 304])
@pytest.mark.asyncio
async def test_non_200_status_classified_as_unknown_http_status(
    status: int,
) -> None:
    """1xx / 3xx 状态 → ``UNKNOWN_HTTP_STATUS`` + Done(ERROR)。"""

    runner = AsyncOpenAIRunner(
        spec=make_spec(max_retries=0),
        cancellation_token=ControllableCancellationToken(),
    )
    session = FakeSession()
    session.enqueue_response(
        FakeResponseSpec(
            status=status,
            headers={"Content-Type": "application/json"},
            body_chunks=[b""],
        )
    )
    _install_session(runner, session)

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    events = []
    async for ev in runner.call(msgs, make_options(stream=False), [], structured_output=None):
        events.append(ev)

    # 不得透到 parser 路径。
    assert not any(
        e.type is RunnerEventType.RUNNER_CONTENT_COMPLETED for e in events
    )
    assert events[-2].type is RunnerEventType.RUNNER_HTTP_ERROR
    err = events[-2].data
    assert isinstance(err, RunnerHTTPErrorData)
    assert err.error_code is RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS
    assert err.http_status == status
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
    await runner.close()
