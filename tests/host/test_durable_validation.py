"""Host durable 私有标量校验 helper 测试。"""

from __future__ import annotations

from typing import cast

import pytest

from dayu.host.durable._validation import (
    require_non_empty_text,
    require_optional_non_empty_text,
)
from dayu.host.durable.errors import HostDurableError


def test_require_non_empty_text_rejects_runtime_non_text_values() -> None:
    """必填文本校验对运行时非文本值抛出结构化 durable error。"""

    for value in (cast(str, None), cast(str, 123), cast(str, b"text")):
        with pytest.raises(HostDurableError) as error_info:
            require_non_empty_text(value, field_name="field")
        assert str(error_info.value) == "field must be non-empty"


def test_require_non_empty_text_preserves_string_behavior() -> None:
    """必填文本校验保留有效、空字符串与纯空白字符串行为。"""

    require_non_empty_text("value", field_name="field")
    for value in ("", " \t\n"):
        with pytest.raises(HostDurableError) as error_info:
            require_non_empty_text(value, field_name="field")
        assert str(error_info.value) == "field must be non-empty"


def test_require_optional_non_empty_text_rejects_runtime_non_text_values() -> None:
    """可选文本校验对运行时非文本值抛出结构化 durable error。"""

    require_optional_non_empty_text(None, field_name="field")
    require_optional_non_empty_text("value", field_name="field")
    for value in (cast(str | None, 123), cast(str | None, b"text"), "", " \t\n"):
        with pytest.raises(HostDurableError) as error_info:
            require_optional_non_empty_text(value, field_name="field")
        assert str(error_info.value) == "field must be non-empty when provided"
