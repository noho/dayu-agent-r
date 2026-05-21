"""Dayu 公共运行时基础设施包。

``dayu.runtime`` 是层中立的 runtime 基础设施包，承载层中立、运行期通用、
可被 :mod:`dayu.engine` / ``dayu.host`` / ``dayu.service`` / ``dayu.ui`` /
``dayu.fins`` 复用的基础能力（日志装配、协作式取消等待 / race helper、
  cross-process lane、同步 filelock wrapper、层中立工具发现装配、层中立配置加载、
  层中立 runtime 位置解析、层中立 scene manifest 装配、层中立工具截断声明补齐、
  层中立 assembly 选择与 allowlist 合并）。

硬约束（架构）：

- ``dayu.runtime.*`` 不得 ``import dayu.engine`` /
  ``dayu.host`` / ``dayu.service`` / ``dayu.ui`` / ``dayu.fins``，
  以及它们的任意子模块。
- 各层需要公共运行时能力时，必须优先复用或扩展 ``dayu.runtime``，
  禁止在各层自行实现语义不一致的重复 runtime helper。
- ``dayu.engine`` **不得** ``import dayu.runtime.log``：Engine 仅用 stdlib
  ``logging.getLogger(__name__)`` 获得 logger，由上层（Host / CLI）通过
  :mod:`dayu.runtime.log` 装配；Engine **允许** ``import``
  :mod:`dayu.runtime.cancellation` 与无装配副作用的
  :mod:`dayu.runtime.log_levels`。

本包不导出业务语义、不持有 Host 治理状态、不持有 Engine 协议状态机。
当前包含 ``dayu.runtime.lane``、``dayu.runtime.filelock``、
``dayu.runtime.tools_discovery``、``dayu.runtime.config_loader`` 与
``dayu.runtime.location``、``dayu.runtime.scene_prepare``、
``dayu.runtime.tool_truncation``、``dayu.runtime.assembly`` 等层中立
runtime 能力；包根不 re-export
这些模块符号。
"""

from __future__ import annotations

__all__: list[str] = []
