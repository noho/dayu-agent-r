"""argparse ``SystemExit`` 退出码归一化契约测试。"""

from __future__ import annotations

import pytest

from dayu.runtime.argparse_exit import normalize_argparse_system_exit_code


@pytest.mark.parametrize("exit_code", (0, 2, -7))
def test_normalize_argparse_system_exit_code_preserves_integer_codes(
    exit_code: int,
) -> None:
    """归一化必须保留 argparse 已提供的整数退出码。

    Args:
        exit_code: ``SystemExit`` 携带的整数退出码。

    Returns:
        无。

    Raises:
        AssertionError: 归一化结果改变原始整数退出码时抛出。
    """

    assert normalize_argparse_system_exit_code(SystemExit(exit_code)) == exit_code


@pytest.mark.parametrize("exit_code", (None, "usage error", ("usage error",)))
def test_normalize_argparse_system_exit_code_uses_parser_error_for_non_integer_codes(
    exit_code: None | str | tuple[str],
) -> None:
    """非整数 ``SystemExit.code`` 必须归一为 argparse 的解析错误码。

    Args:
        exit_code: ``SystemExit`` 携带的非整数退出信息。

    Returns:
        无。

    Raises:
        AssertionError: 归一化结果不是 argparse 解析错误码时抛出。
    """

    assert normalize_argparse_system_exit_code(SystemExit(exit_code)) == 2
