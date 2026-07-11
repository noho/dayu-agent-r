"""``HTTPClient.close()`` 幂等性与资源释放测试。"""

from __future__ import annotations

import pytest

from dayu.engine.runners.openai.http_client import HTTPClient
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

from tests.host.fake_cancellation import ControllableCancellationToken
from tests.engine.runners.openai._factories import make_spec
from tests.engine.runners.openai._fakes import FakeSession


@pytest.mark.asyncio
async def test_http_client_close_idempotent() -> None:
    """``close`` 二次调用安全、状态置位。"""

    client = HTTPClient(timeout_seconds=1.0)
    fake_session = FakeSession()
    client._session = fake_session  # type: ignore[attr-defined]
    await client.close()
    assert client.is_closed is True
    assert client._session is None  # type: ignore[attr-defined]
    assert fake_session.closed is True
    # 第二次调用不应抛异常
    await client.close()


@pytest.mark.asyncio
async def test_runner_close_releases_resources() -> None:
    """``AsyncOpenAIRunner.close`` 应触发 HTTPClient.close。"""

    runner = AsyncOpenAIRunner(
        spec=make_spec(), cancellation_token=ControllableCancellationToken()
    )
    fake_session = FakeSession()
    runner._http_client._session = fake_session  # type: ignore[attr-defined]
    await runner.close()
    assert runner._http_client.is_closed is True  # type: ignore[attr-defined]
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_close_after_cancel_does_not_raise() -> None:
    """已取消状态下 ``close`` 不应抛异常。"""

    token = ControllableCancellationToken()
    token.request_cancel()
    runner = AsyncOpenAIRunner(spec=make_spec(), cancellation_token=token)
    fake_session = FakeSession()
    runner._http_client._session = fake_session  # type: ignore[attr-defined]
    await runner.close()
    assert runner._http_client.is_closed is True  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_session_property_after_close_raises() -> None:
    """关闭后再取 ``session()`` 应抛 :class:`RuntimeError`。"""

    client = HTTPClient(timeout_seconds=1.0)
    await client.close()
    import pytest

    with pytest.raises(RuntimeError):
        client.session()
