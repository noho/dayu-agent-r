"""Dayu 公共运行时基础设施包。

``dayu.runtime`` 是层中立的 runtime 基础设施包，承载层中立、运行期通用、
可被 :mod:`dayu.engine` / ``dayu.host`` / ``dayu.service`` / ``dayu.ui`` /
``dayu.fins`` 复用的基础能力（日志装配、协作式取消等待 / race helper）。

硬约束（架构）：

- ``dayu.runtime.*`` 不得 ``import dayu.engine`` /
  ``dayu.host`` / ``dayu.service`` / ``dayu.ui`` / ``dayu.fins``，
  以及它们的任意子模块。
- 各层需要公共运行时能力时，必须优先复用或扩展 ``dayu.runtime``，
  禁止在各层自行实现语义不一致的重复 runtime helper。
- ``dayu.engine`` **不得** ``import dayu.runtime.log``：Engine 仅用 stdlib
  ``logging.getLogger(__name__)`` 获得 logger，由上层（Host / CLI）通过
  :mod:`dayu.runtime.log` 装配；Engine **允许** ``import``
  :mod:`dayu.runtime.cancellation`。

本包不导出业务语义、不持有 Host 治理状态、不持有 Engine 协议状态机。
"""

from __future__ import annotations

__all__: list[str] = []
