"""Host 内部文本辅助函数测试。"""

from __future__ import annotations

from dayu.host._text import truncate_text


def test_truncate_text_returns_empty_when_limit_is_not_positive() -> None:
    """验证非正 limit 返回空文本。

    :returns: 无返回值。
    :raises AssertionError: 行为不符合预期时抛出。
    """

    assert truncate_text(text="abc", limit=0) == ""
    assert truncate_text(text="abc", limit=-1) == ""


def test_truncate_text_keeps_text_within_limit() -> None:
    """验证未超限文本保持原样。

    :returns: 无返回值。
    :raises AssertionError: 行为不符合预期时抛出。
    """

    assert truncate_text(text="abc", limit=3) == "abc"
    assert truncate_text(text="abc", limit=4) == "abc"


def test_truncate_text_appends_suffix_after_limit_prefix() -> None:
    """验证超限文本按前缀裁剪并追加统一后缀。

    :returns: 无返回值。
    :raises AssertionError: 行为不符合预期时抛出。
    """

    assert truncate_text(text="abcdef", limit=3) == "abc...[已裁剪]"
