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
    :param resume_token: 恢复时所需的中性 token；语义由 Host 拥有。
    """

    await_kind: ToolAwaitKind
    deadline: datetime | None
    resume_token: str


@dataclass(frozen=True, slots=True)
class ToolAwaitSnapshot:
    """工具等待时点快照。

    :param snapshot_id: 快照唯一 id。
    :param captured_at: 快照采集时间。
    """

    snapshot_id: str
    captured_at: datetime


__all__ = ["ToolAwaitKind", "ToolAwaitSpec", "ToolAwaitSnapshot"]
