"""协作式取消观察原语。

本模块提供 :class:`CancellationToken` Protocol 作为 Engine 公共取消
**观察**契约。Engine 内部 Agent / Runner / 工具执行只通过本契约**观察**
取消状态；治理真源（取消触发、reason 设置、accept/finish 时间戳）由
Host 拥有，本 Phase 不实现。

取消的**公共终态**由上层 Engine 的结构化事件与 run outcome 表达。
Engine 不把任何取消异常作为公共 contract——内部协作式控制流若需要
异常语义，由实现 Phase 在 Engine 内部私有模块定义，不作为 Host 可
依赖的接口。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class CancellationToken(Protocol):
    """取消观察 Protocol。

    本协议只描述 Engine 侧的**观察面**；具体实现（Host 控制、CLI 信号、
    UI 取消按钮）不属于 Engine 公共契约。
    """

    def is_cancelled(self) -> bool:
        """返回当前是否已被请求取消。

        :returns: 已请求取消返回 ``True``，否则 ``False``。
        """
        ...

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 若已取消则返回中性字符串原因；未取消返回 ``None``。
        """
        ...

    def requested_at(self) -> datetime | None:
        """返回取消请求时间戳。

        :returns: 若已请求取消返回时间戳；未请求返回 ``None``。
        """
        ...


__all__ = ["CancellationToken"]
