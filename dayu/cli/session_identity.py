"""CLI Session 身份展示与共享 Agent label slot 映射 helper。

本模块只处理 CLI 用户可见的 Session kind / label 投影，不调用 Host、不读取
durable store，也不判断 Host 状态机。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dayu.cli.host_context import (
    CLI_AGENT_SESSION_SCOPE,
    CLI_AGENT_SLOT_KEY_PREFIX,
    cli_label_slot_key,
)
from dayu.host.api import SessionSlotRef

SESSION_LABEL_DISPLAY_EMPTY: str = "-"


class CliSessionDisplayKind(StrEnum):
    """CLI Session 列表展示类型。"""

    ANONYMOUS = "anonymous"
    LABELED = "labeled"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class CliSessionDisplayIdentity:
    """CLI Session 列表展示身份。

    :param kind: Session 展示类型。
    :param label: 展示用 label；匿名 Session 固定为 ``-``。
    """

    kind: CliSessionDisplayKind
    label: str


def slot_ref_for_cli_label(label: str) -> SessionSlotRef:
    """把 CLI label selector 映射为 Host public slot ref。

    :param label: 用户输入的 label。
    :returns: 对应 Host public slot ref。
    :raises ValueError: label 为空或仅包含空白时抛出。
    """

    return SessionSlotRef(
        scope=CLI_AGENT_SESSION_SCOPE,
        slot_key=cli_label_slot_key(label),
    )


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
    labeled_alias = _label_suffix(
        scope=slot.scope,
        slot_key=slot.slot_key,
        expected_scope=CLI_AGENT_SESSION_SCOPE,
        expected_prefix=CLI_AGENT_SLOT_KEY_PREFIX,
    )
    if labeled_alias is not None:
        return CliSessionDisplayIdentity(
            kind=CliSessionDisplayKind.LABELED,
            label=labeled_alias,
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
    "SESSION_LABEL_DISPLAY_EMPTY",
    "display_identity_from_slot",
    "slot_ref_for_cli_label",
)
