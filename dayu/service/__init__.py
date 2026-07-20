"""Dayu Service 层 composition 边界包。

本包承载 Host 外部的 Service 组合 helper。Service 可以读取 runtime typed
config、scene 装配结果与工具发现结果，并将它们映射为 Host public typed
inputs；Service 不持有 Host durable truth，不实现 Engine 状态机，也不让
``dayu.runtime`` 反向依赖业务层。
"""

from __future__ import annotations

from dayu.service.host_admin import (
    ServiceHostAdminRequest,
    ServiceHostAdminResult,
    prepare_host_admin,
)

__all__ = [
    "ServiceHostAdminRequest",
    "ServiceHostAdminResult",
    "prepare_host_admin",
]
