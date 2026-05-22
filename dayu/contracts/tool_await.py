"""工具等待规约与快照契约。

本模块定义长事务工具调用的等待规约 :class:`ToolAwaitSpec` 与执行快照
:class:`ToolAwaitSnapshot`。两者只承载 Engine 公共契约必要的中性事实，
**不**预留任意属性袋（防止退化为弱类型语义袋）。

:class:`ToolAwaitKind` 在 Phase 0 仅落地保守初始成员
:attr:`ToolAwaitKind.EXTERNAL_JOB`；新增成员需消费 Phase 单独评审引入。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

_MAX_RESUME_TOKEN_LENGTH: Final[int] = 2048


class ToolAwaitKind(StrEnum):
    """工具等待类型枚举。

    Phase 0 仅落地一种等待类型：

    - ``EXTERNAL_JOB``：等待 Host 托管的外部异步作业（长事务）。

    其它等待类型留给后续 Phase 与 Host ToolRuntime 协议同步评审引入。
    """

    EXTERNAL_JOB = "external_job"


@dataclass(frozen=True, slots=True)
class ToolAwaitSpec:
    """工具等待规约。

    :param await_kind: 等待类型；Phase 0 仅 :attr:`ToolAwaitKind.EXTERNAL_JOB`。
    :param deadline: 截止时间；``None`` 表示由 Host 兜底策略决定。
    :param resume_token: 恢复时所需的 Host-owned opaque reference。Engine
        只透传该值，不解析、不签发、不把它视为授权凭据或可执行 payload。
    """

    await_kind: ToolAwaitKind
    deadline: datetime | None
    resume_token: str

    def __post_init__(self) -> None:
        """校验等待恢复 token 的基础边界。

        :returns: ``None``。
        :raises TypeError: ``await_kind`` 类型非法时抛出。
        :raises ValueError: ``resume_token`` 为空或超过长度上限时抛出。
        """

        if not isinstance(self.await_kind, ToolAwaitKind):
            raise TypeError("ToolAwaitSpec.await_kind must be ToolAwaitKind")
        if self.resume_token.strip() == "":
            raise ValueError("ToolAwaitSpec.resume_token must not be empty")
        if len(self.resume_token) > _MAX_RESUME_TOKEN_LENGTH:
            raise ValueError("ToolAwaitSpec.resume_token is too long")


@dataclass(frozen=True, slots=True)
class ToolAwaitSnapshot:
    """工具等待时点快照引用。

    快照内容由 Host / ToolRuntime 持有；Engine 只透传 opaque
    ``snapshot_id`` 与采集时间，不提供快照检索机制，也不在本类型中承载
    业务状态或任意属性袋。

    :param snapshot_id: 快照唯一 id。
    :param captured_at: 快照采集时间。
    """

    snapshot_id: str
    captured_at: datetime

    def __post_init__(self) -> None:
        """校验等待快照引用。

        :returns: ``None``。
        :raises ValueError: ``snapshot_id`` 为空时抛出。
        """

        if self.snapshot_id.strip() == "":
            raise ValueError("ToolAwaitSnapshot.snapshot_id must not be empty")


__all__ = ["ToolAwaitKind", "ToolAwaitSpec", "ToolAwaitSnapshot"]
