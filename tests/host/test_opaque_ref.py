"""Host 中立 opaque ref 校验测试。"""

from __future__ import annotations

from typing import cast

import pytest

from dayu.host.opaque_ref import (
    host_neutral_opaque_ref_kinds,
    validate_host_neutral_opaque_ref_kind,
    validate_host_neutral_opaque_ref_text,
)


def test_validate_host_neutral_opaque_ref_text_accepts_known_kind() -> None:
    """合法 ``kind:ref_id`` 文本应通过校验。"""

    validate_host_neutral_opaque_ref_text("source:filing-2025-10k")


@pytest.mark.parametrize("value", ("", "   ", "source:", "source: \t"))
def test_validate_host_neutral_opaque_ref_text_rejects_empty_parts(
    value: str,
) -> None:
    """空文本或空 ref id 应被拒绝。"""

    with pytest.raises(ValueError):
        validate_host_neutral_opaque_ref_text(value)


def test_validate_host_neutral_opaque_ref_text_rejects_non_string() -> None:
    """opaque ref 文本必须是字符串。"""

    with pytest.raises(TypeError, match="opaque ref must be str"):
        validate_host_neutral_opaque_ref_text(cast(str, 123))


def test_validate_host_neutral_opaque_ref_text_requires_kind_prefix() -> None:
    """缺少 kind 前缀的文本应被拒绝。"""

    with pytest.raises(ValueError, match="requires kind prefix"):
        validate_host_neutral_opaque_ref_text("filing-2025-10k")


def test_validate_host_neutral_opaque_ref_kind_rejects_invalid_kind() -> None:
    """Host 中立 opaque ref kind 使用封闭集合。"""

    with pytest.raises(ValueError, match="kind is invalid"):
        validate_host_neutral_opaque_ref_kind("company")


def test_validate_host_neutral_opaque_ref_kind_rejects_non_string() -> None:
    """opaque ref kind 必须是字符串。"""

    with pytest.raises(TypeError, match="opaque ref kind must be str"):
        validate_host_neutral_opaque_ref_kind(cast(str, 123))


def test_host_neutral_opaque_ref_kinds_returns_closed_set() -> None:
    """公开 helper 返回当前 Host 中立 kind 闭集。"""

    assert host_neutral_opaque_ref_kinds() == frozenset(
        {
            "source",
            "chunk",
            "entity",
            "subject",
            "topic",
            "evidence",
            "payload",
            "external",
        }
    )
