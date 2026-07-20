"""OpenAI-compatible context overflow classifier 测试。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import RunnerHTTPErrorCode
from dayu.engine.contracts.runner_events import ContextOverflowDetectionKind
from dayu.engine.runners.openai.error_classifier import (
    classify_http_status,
    detect_context_overflow,
    is_retriable,
)


@pytest.mark.parametrize(
    "response_text",
    (
        '{"error":{"code":"context_length_exceeded","message":"too long"}}',
        "maximum context length is 128000 tokens",
        "total message token length exceed model limit",
        "model's maximum context length is 200000 tokens",
        "range of input length should be [1, 128000]",
        "model requires more context than available",
    ),
)
def test_detect_context_overflow_old_provider_signal_matrix(
    response_text: str,
) -> None:
    """覆盖 OLD 多 provider context overflow 信号矩阵。"""

    detection = detect_context_overflow(
        http_status=400,
        response_text=response_text,
    )
    assert detection.kind in (
        ContextOverflowDetectionKind.STRUCTURED_CODE,
        ContextOverflowDetectionKind.MESSAGE_MARKER_FALLBACK,
    )


@pytest.mark.parametrize(
    "response_text",
    (
        '{"error":{"code":"invalid_request_error","message":"bad param"}}',
        "ordinary client error",
        "rate limit exceeded",
    ),
)
def test_detect_context_overflow_rejects_plain_client_errors(
    response_text: str,
) -> None:
    """普通 400 / client error 不得误触发 context compact。"""

    detection = detect_context_overflow(
        http_status=400,
        response_text=response_text,
    )
    assert detection.kind is ContextOverflowDetectionKind.NOT_OVERFLOW


def test_structured_non_overflow_code_blocks_message_marker_fallback() -> None:
    """结构化 code 明确非 overflow 时不得被 message marker 覆盖。"""

    detection = detect_context_overflow(
        http_status=400,
        response_text=(
            '{"error":{"code":"invalid_request_error",'
            '"message":"context length exceeded by malformed parameter"}}'
        ),
    )
    assert detection.kind is ContextOverflowDetectionKind.NOT_OVERFLOW


def test_context_length_error_code_is_not_runner_retriable() -> None:
    """context overflow 不是 Runner 内部 retry，后续由 Host compact 接管。"""

    assert (
        classify_http_status(400) is RunnerHTTPErrorCode.CLIENT_ERROR
    )
    assert not is_retriable(RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED)


def test_detect_context_overflow_accepts_bounded_5xx_body_marker() -> None:
    """5xx 错误体中明确 overflow marker 时也应触发 context compact。"""

    detection = detect_context_overflow(
        http_status=500,
        response_text="context length exceeded while upstream recovered",
    )
    assert detection.kind is ContextOverflowDetectionKind.MESSAGE_MARKER_FALLBACK
    assert detection.diagnostic_code == "context_overflow_message_marker_fallback"
