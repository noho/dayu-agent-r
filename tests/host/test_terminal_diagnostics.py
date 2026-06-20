"""Host terminal 诊断后缀 helper 测试。"""

from __future__ import annotations

from dayu.host._terminal_diagnostics import (
    _TERMINAL_DIAGNOSTIC_ID_MAX_CHARS,
    _append_terminal_diagnostic_suffix,
)

_MESSAGE = "provider failed"
_PROVIDER_REQUEST_ID = "provider-req-1"
_CLIENT_CORRELATION_ID = "client-correlation-1"


def test_terminal_diagnostic_suffix_includes_only_provider_id() -> None:
    """仅 provider_request_id 存在时只追加 provider 诊断行。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    message = _append_terminal_diagnostic_suffix(
        _MESSAGE,
        provider_request_id=_PROVIDER_REQUEST_ID,
        client_correlation_id=None,
    )

    assert message == f"{_MESSAGE}\nprovider_request_id={_PROVIDER_REQUEST_ID}"


def test_terminal_diagnostic_suffix_includes_only_client_id() -> None:
    """仅 client_correlation_id 存在时只追加 client 诊断行。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    message = _append_terminal_diagnostic_suffix(
        _MESSAGE,
        provider_request_id=None,
        client_correlation_id=_CLIENT_CORRELATION_ID,
    )

    assert message == f"{_MESSAGE}\nclient_correlation_id={_CLIENT_CORRELATION_ID}"


def test_terminal_diagnostic_suffix_includes_both_ids_in_stable_order() -> None:
    """两个诊断 id 同时存在时按 provider、client 顺序追加。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    message = _append_terminal_diagnostic_suffix(
        _MESSAGE,
        provider_request_id=_PROVIDER_REQUEST_ID,
        client_correlation_id=_CLIENT_CORRELATION_ID,
    )

    assert message == (
        f"{_MESSAGE}\n"
        f"provider_request_id={_PROVIDER_REQUEST_ID}\n"
        f"client_correlation_id={_CLIENT_CORRELATION_ID}"
    )


def test_terminal_diagnostic_suffix_returns_original_message_when_ids_absent() -> None:
    """两个诊断 id 都缺失时不改写原始消息。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    message = _append_terminal_diagnostic_suffix(
        _MESSAGE,
        provider_request_id=None,
        client_correlation_id=None,
    )

    assert message == _MESSAGE


def test_terminal_diagnostic_suffix_returns_none_when_message_and_ids_absent() -> None:
    """消息和两个诊断 id 都缺失时返回 ``None``。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    message = _append_terminal_diagnostic_suffix(
        None,
        provider_request_id=None,
        client_correlation_id=None,
    )

    assert message is None


def test_terminal_diagnostic_suffix_uses_suffix_when_message_is_none() -> None:
    """消息为 ``None`` 且诊断 id 存在时返回纯诊断后缀。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    message = _append_terminal_diagnostic_suffix(
        None,
        provider_request_id=_PROVIDER_REQUEST_ID,
        client_correlation_id=_CLIENT_CORRELATION_ID,
    )

    assert message == (
        f"provider_request_id={_PROVIDER_REQUEST_ID}\n"
        f"client_correlation_id={_CLIENT_CORRELATION_ID}"
    )


def test_terminal_diagnostic_suffix_uses_suffix_when_message_is_empty() -> None:
    """消息为空字符串且诊断 id 存在时返回纯诊断后缀。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    message = _append_terminal_diagnostic_suffix(
        "",
        provider_request_id=None,
        client_correlation_id=_CLIENT_CORRELATION_ID,
    )

    assert message == f"client_correlation_id={_CLIENT_CORRELATION_ID}"


def test_terminal_diagnostic_suffix_truncates_ids() -> None:
    """诊断 id 超过展示上限时按上限截断。

    :returns: ``None``。
    :raises AssertionError: helper 输出不符合预期时抛出。
    """

    long_provider_request_id = "p" * (_TERMINAL_DIAGNOSTIC_ID_MAX_CHARS + 1)
    expected_provider_request_id = "p" * _TERMINAL_DIAGNOSTIC_ID_MAX_CHARS

    message = _append_terminal_diagnostic_suffix(
        _MESSAGE,
        provider_request_id=long_provider_request_id,
        client_correlation_id=None,
    )

    assert message == (
        f"{_MESSAGE}\nprovider_request_id={expected_provider_request_id}"
    )
