"""重试与退避策略。

本模块提供 :func:`compute_retry_decision` 纯函数：根据 HTTP
``Retry-After`` 头（若存在）、本次错误的中性枚举与已尝试次数，产出
:class:`_RetryDecision`。

策略（与 OLD ``async_openai_runner.py`` 一致）：

- 若错误不可重试（见
  :func:`~dayu.engine.runners.openai.error_classifier.is_retriable`）→
  ``should_retry=False``。
- 若已尝试次数 ``>= spec.max_retries`` → ``should_retry=False``。
- 若 ``Retry-After`` 头存在且为正数 → 优先使用，``should_retry=True``。
- 否则使用指数退避：``min(2 ** (attempt - 1), backoff_cap)`` 秒，
  ``should_retry=True``。
"""

from __future__ import annotations

from dayu.engine.contracts.runner_events import RunnerHTTPErrorCode
from dayu.engine.runners.openai._types import _RetryDecision
from dayu.engine.runners.openai.error_classifier import is_retriable

_DEFAULT_BACKOFF_CAP_SECONDS: float = 30.0


def parse_retry_after(retry_after_header: str | None) -> float | None:
    """解析 HTTP ``Retry-After`` 头。

    :param retry_after_header: 原始头字符串；为 ``None`` 表示未提供。
    :returns: 正数秒值；无效或负值返回 ``None``。

    本函数仅处理「秒数」形态；HTTP-date 形态由调用方按需扩展，本
    Phase 不实现。
    """

    if retry_after_header is None:
        return None
    text = retry_after_header.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value <= 0.0:
        return None
    return value


def compute_retry_decision(
    *,
    error_code: RunnerHTTPErrorCode,
    attempt: int,
    max_retries: int,
    retry_after_seconds: float | None,
    backoff_cap_seconds: float = _DEFAULT_BACKOFF_CAP_SECONDS,
) -> _RetryDecision:
    """计算下一次重试决策。

    :param error_code: 本次错误的中性枚举。
    :param attempt: 已尝试次数（首次失败后调用本函数时传 ``1``）。
    :param max_retries: ``RunnerSpec.max_retries`` 上限；为 ``0`` 表示
        不重试。
    :param retry_after_seconds: HTTP ``Retry-After`` 解析后的秒数；为
        ``None`` 表示无该头。
    :param backoff_cap_seconds: 指数退避上限秒数。
    :returns: :class:`_RetryDecision` 决策。
    """

    if not is_retriable(error_code):
        return _RetryDecision(
            should_retry=False, sleep_seconds=0.0, attempt=attempt
        )
    if attempt > max_retries:
        return _RetryDecision(
            should_retry=False, sleep_seconds=0.0, attempt=attempt
        )
    if retry_after_seconds is not None:
        return _RetryDecision(
            should_retry=True,
            sleep_seconds=retry_after_seconds,
            attempt=attempt,
        )
    sleep_seconds = min(2.0 ** (attempt - 1), backoff_cap_seconds)
    return _RetryDecision(
        should_retry=True, sleep_seconds=sleep_seconds, attempt=attempt
    )


__all__ = ["compute_retry_decision", "parse_retry_after"]
