"""重试退避策略测试。

覆盖：

- ``parse_retry_after`` 各分支。
- 指数退避基线（无 Retry-After）。
- ``Retry-After`` 头优先于指数退避。
- ``max_retries`` 上限耗尽。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import format_datetime

import pytest

from dayu.engine.contracts.runner_events import RunnerHTTPErrorCode
from dayu.engine.runners.openai.retry_policy import (
    compute_retry_decision,
    parse_retry_after,
)


def test_parse_retry_after_valid_seconds() -> None:
    """``Retry-After: 3`` → ``3.0``。"""

    assert parse_retry_after("3") == 3.0


def test_parse_retry_after_float() -> None:
    """``Retry-After: 0.5`` → ``0.5``。"""

    assert parse_retry_after("0.5") == 0.5


def test_parse_retry_after_none_returns_none() -> None:
    """``None`` 输入返回 ``None``。"""

    assert parse_retry_after(None) is None


def test_parse_retry_after_empty_returns_none() -> None:
    """空字符串返回 ``None``。"""

    assert parse_retry_after("") is None
    assert parse_retry_after("   ") is None


def test_parse_retry_after_invalid_returns_none() -> None:
    """非法字符串与非未来 HTTP-date 返回 ``None``。"""

    assert parse_retry_after("not-a-date") is None
    assert (
        parse_retry_after(
            "Wed, 21 Oct 2015 07:28:00 GMT",
            now=datetime(2026, 6, 4, tzinfo=UTC),
        )
        is None
    )


def test_parse_retry_after_negative_returns_none() -> None:
    """负值或零返回 ``None``。"""

    assert parse_retry_after("-1") is None
    assert parse_retry_after("0") is None


def test_parse_retry_after_http_date_uses_future_delay_seconds() -> None:
    """HTTP-date 形态返回相对当前时间的正数秒值。"""

    now = datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC)
    retry_at = datetime(2026, 6, 4, 12, 0, 7, tzinfo=UTC)

    assert parse_retry_after(format_datetime(retry_at), now=now) == 7.0


def test_compute_retry_decision_uses_retry_after() -> None:
    """``Retry-After=3`` 优先于指数退避。"""

    decision = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
        attempt=1,
        max_retries=3,
        retry_after_seconds=3.0,
    )
    assert decision.should_retry is True
    assert decision.sleep_seconds == 3.0


def test_rate_limit_no_retry_after_first_backoff_is_4_seconds() -> None:
    """OLD：429 无 ``Retry-After`` 首次 backoff 4s。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
        attempt=1,
        max_retries=5,
        retry_after_seconds=None,
    )
    assert d.should_retry is True
    assert d.sleep_seconds == 4.0


def test_rate_limit_no_retry_after_capped_at_60_seconds() -> None:
    """OLD：429 无 ``Retry-After`` 指数退避 cap 60s。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
        attempt=10,
        max_retries=20,
        retry_after_seconds=None,
    )
    assert d.should_retry is True
    assert d.sleep_seconds == 60.0


def test_rate_limit_retry_after_capped_at_120_seconds() -> None:
    """OLD：429 ``Retry-After`` cap 120s。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
        attempt=1,
        max_retries=5,
        retry_after_seconds=999.0,
    )
    assert d.should_retry is True
    assert d.sleep_seconds == 120.0


def test_non_rate_limit_retry_after_capped_by_stable_retry_after_limit() -> None:
    """非 429 路径的 ``Retry-After`` 同样受稳定上限保护。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        attempt=1,
        max_retries=5,
        retry_after_seconds=999.0,
    )
    assert d.should_retry is True
    assert d.sleep_seconds == 120.0


def test_compute_retry_decision_exponential_backoff() -> None:
    """无 ``Retry-After`` 时使用 ``2 ** (attempt-1)`` 指数退避。"""

    d1 = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        attempt=1,
        max_retries=3,
        retry_after_seconds=None,
    )
    d2 = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        attempt=2,
        max_retries=3,
        retry_after_seconds=None,
    )
    d3 = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        attempt=3,
        max_retries=3,
        retry_after_seconds=None,
    )
    assert d1.sleep_seconds == 1.0
    assert d2.sleep_seconds == 2.0
    assert d3.sleep_seconds == 4.0


def test_compute_retry_decision_capped_backoff() -> None:
    """指数退避受 ``backoff_cap_seconds`` 上限。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        attempt=10,
        max_retries=20,
        retry_after_seconds=None,
        backoff_cap_seconds=5.0,
    )
    assert d.sleep_seconds == 5.0


def test_compute_retry_decision_exhausted_after_retry_count_used() -> None:
    """``max_retries`` 表示首败后的重试次数。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        attempt=2,
        max_retries=1,
        retry_after_seconds=None,
    )
    assert d.should_retry is False


def test_compute_retry_decision_zero_max_retries_disables_retry() -> None:
    """``max_retries=0`` 时首次失败后不得重试。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        attempt=1,
        max_retries=0,
        retry_after_seconds=None,
    )
    assert d.should_retry is False


def test_compute_retry_decision_non_retriable() -> None:
    """``CLIENT_ERROR`` 永不重试。"""

    d = compute_retry_decision(
        error_code=RunnerHTTPErrorCode.CLIENT_ERROR,
        attempt=1,
        max_retries=10,
        retry_after_seconds=None,
    )
    assert d.should_retry is False


@pytest.mark.asyncio
async def test_runner_sleeps_between_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runner 重试时使用 ``Retry-After`` / 指数退避调用 ``asyncio.sleep``。"""

    from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
    from dayu.engine.contracts.runner_events import RunnerEventType
    from dayu.engine.runners.openai.runner import AsyncOpenAIRunner

    from tests.host.fake_cancellation import ControllableCancellationToken
    from tests.engine.runners.openai._factories import (
        make_options,
        make_spec,
    )
    from tests.engine.runners.openai._fakes import (
        FakeResponseSpec,
        FakeSession,
    )

    real_sleep = asyncio.sleep
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    runner = AsyncOpenAIRunner(
        spec=make_spec(max_retries=2),
        cancellation_token=ControllableCancellationToken(),
    )
    session = FakeSession()
    # 第一次 429 with Retry-After=3 → sleep 3
    session.enqueue_response(
        FakeResponseSpec(
            status=429,
            headers={"Content-Type": "application/json", "Retry-After": "3"},
            body_chunks=[b"limit"],
        )
    )
    # 第二次 500（无 Retry-After）→ 指数退避 attempt=2 → 2.0
    session.enqueue_response(
        FakeResponseSpec(
            status=500,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"err"],
        )
    )
    # 第三次 500 → 重试已耗尽，作为终态错误 emit
    session.enqueue_response(
        FakeResponseSpec(
            status=500,
            headers={"Content-Type": "application/json"},
            body_chunks=[b"err"],
        )
    )
    runner._http_client._session = session  # type: ignore[attr-defined]

    msgs = [UserMessage(role=AgentMessageRole.USER, content="hi")]
    final_events = []
    async for ev in runner.call(msgs, make_options(stream=False), [], structured_output=None):
        final_events.append(ev)
    await runner.close()

    # ``await_or_cancel`` 的取消观察任务也在用 ``asyncio.sleep`` 轮询，
    # 默认间隔 ``0.05``；过滤后只看真正的 retry sleep。
    retry_sleeps = [s for s in sleeps if s != 0.05 and s != 0]
    assert retry_sleeps == [3.0, 2.0]
    assert final_events[-1].type is RunnerEventType.RUNNER_DONE
