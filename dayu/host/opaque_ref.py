"""Host 中立 opaque ref 校验工具。

本模块只定义 Host 层共享的 opaque ref 文本校验规则，用于 compaction
proposal、canonical payload validator 与 memory projection 在同一语义下拒绝
自由业务字符串。
"""

from __future__ import annotations

_HOST_NEUTRAL_OPAQUE_REF_KINDS = frozenset(
    (
        "source",
        "chunk",
        "entity",
        "subject",
        "topic",
        "evidence",
        "payload",
        "external",
    )
)


def validate_host_neutral_opaque_ref_text(value: str) -> None:
    """校验 ``kind:ref_id`` 形式的 Host 中立 opaque ref 文本。

    :param value: opaque ref 文本。
    :returns: ``None``。
    :raises TypeError: 输入不是字符串时抛出。
    :raises ValueError: 文本为空、缺少 kind 前缀、kind 非法或 ref id 为空时抛出。
    """

    if not isinstance(value, str):
        raise TypeError("opaque ref must be str")
    if value.strip() == "":
        raise ValueError("opaque ref is required")
    if ":" not in value:
        raise ValueError("opaque ref text requires kind prefix")
    kind, ref_id = value.split(":", 1)
    validate_host_neutral_opaque_ref_kind(kind)
    if ref_id.strip() == "":
        raise ValueError("opaque ref id is required")


def validate_host_neutral_opaque_ref_kind(kind: str) -> None:
    """校验 Host 中立 opaque ref kind。

    :param kind: opaque ref kind。
    :returns: ``None``。
    :raises TypeError: kind 不是字符串时抛出。
    :raises ValueError: kind 不在 Host 中立集合内时抛出。
    """

    if not isinstance(kind, str):
        raise TypeError("opaque ref kind must be str")
    if kind not in _HOST_NEUTRAL_OPAQUE_REF_KINDS:
        raise ValueError("opaque ref kind is invalid")


def host_neutral_opaque_ref_kinds() -> frozenset[str]:
    """返回 Host 中立 opaque ref kind 集合。

    :returns: Host 中立 opaque ref kind 集合。
    """

    return _HOST_NEUTRAL_OPAQUE_REF_KINDS
