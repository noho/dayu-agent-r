"""CLI Session 身份展示与 label slot 映射 helper。

本模块只处理 CLI 用户可见的 Session kind / label 投影，不调用 Host、不读取
durable store，也不判断 Host 状态机。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dayu.cli.host_context import (
    INTERACTIVE_SESSION_SCOPE,
    INTERACTIVE_SLOT_KEY_PREFIX,
    PROMPT_SESSION_SCOPE,
    PROMPT_SLOT_KEY_PREFIX,
    interactive_slot_key,
    prompt_slot_key,
)
from dayu.host.api import SessionSlotRef

SESSION_LABEL_DISPLAY_EMPTY: str = "-"


class CliSessionLabelKind(StrEnum):
    """CLI label namespace 类型。"""

    PROMPT = "prompt"
    INTERACTIVE = "interactive"


class CliSessionDisplayKind(StrEnum):
    """CLI Session 列表展示类型。"""

    ANONYMOUS = "anonymous"
    PROMPT = "prompt"
    INTERACTIVE = "interactive"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class CliSessionDisplayIdentity:
    """CLI Session 列表展示身份。

    :param kind: Session 展示类型。
    :param label: 展示用 label；匿名 Session 固定为 ``-``。
    """

    kind: CliSessionDisplayKind
    label: str


def slot_ref_for_cli_label(kind: CliSessionLabelKind, label: str) -> SessionSlotRef:
    """把 CLI label selector 映射为 Host public slot ref。

    :param kind: CLI label namespace。
    :param label: 用户输入的 label。
    :returns: 对应 Host public slot ref。
    :raises TypeError: ``kind`` 不是 ``CliSessionLabelKind`` 时抛出。
    :raises ValueError: label 为空或仅包含空白时抛出。
    """

    if kind is CliSessionLabelKind.PROMPT:
        return SessionSlotRef(
            scope=PROMPT_SESSION_SCOPE,
            slot_key=prompt_slot_key(label),
        )
    if kind is CliSessionLabelKind.INTERACTIVE:
        return SessionSlotRef(
            scope=INTERACTIVE_SESSION_SCOPE,
            slot_key=interactive_slot_key(label),
        )
    raise TypeError("kind must be CliSessionLabelKind")


def display_identity_from_slot(
    slot: SessionSlotRef | None,
) -> CliSessionDisplayIdentity:
    """从 Host slot truth 反解 CLI 列表展示身份。

    :param slot: Host public Session slot；匿名 Session 为 ``None``。
    :returns: CLI 展示用 kind / label。
    :raises Exception: 不主动抛出异常。
    """

    if slot is None:
        return CliSessionDisplayIdentity(
            kind=CliSessionDisplayKind.ANONYMOUS,
            label=SESSION_LABEL_DISPLAY_EMPTY,
        )
    prompt_label = _label_suffix(
        scope=slot.scope,
        slot_key=slot.slot_key,
        expected_scope=PROMPT_SESSION_SCOPE,
        expected_prefix=PROMPT_SLOT_KEY_PREFIX,
    )
    if prompt_label is not None:
        return CliSessionDisplayIdentity(
            kind=CliSessionDisplayKind.PROMPT,
            label=prompt_label,
        )
    interactive_label = _label_suffix(
        scope=slot.scope,
        slot_key=slot.slot_key,
        expected_scope=INTERACTIVE_SESSION_SCOPE,
        expected_prefix=INTERACTIVE_SLOT_KEY_PREFIX,
    )
    if interactive_label is not None:
        return CliSessionDisplayIdentity(
            kind=CliSessionDisplayKind.INTERACTIVE,
            label=interactive_label,
        )
    return CliSessionDisplayIdentity(
        kind=CliSessionDisplayKind.OTHER,
        label=slot.slot_key,
    )


def _label_suffix(
    *,
    scope: str,
    slot_key: str,
    expected_scope: str,
    expected_prefix: str,
) -> str | None:
    """按固定 scope / prefix 反解 label 后缀。

    :param scope: Host slot scope。
    :param slot_key: Host slot key。
    :param expected_scope: CLI namespace 对应 scope。
    :param expected_prefix: CLI namespace 对应 slot key 前缀。
    :returns: 非空 label 后缀；不匹配时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if scope != expected_scope:
        return None
    if not slot_key.startswith(expected_prefix):
        return None
    suffix = slot_key[len(expected_prefix) :]
    if suffix == "":
        return None
    return suffix


__all__: tuple[str, ...] = (
    "CliSessionDisplayIdentity",
    "CliSessionDisplayKind",
    "CliSessionLabelKind",
    "SESSION_LABEL_DISPLAY_EMPTY",
    "display_identity_from_slot",
    "slot_ref_for_cli_label",
)
