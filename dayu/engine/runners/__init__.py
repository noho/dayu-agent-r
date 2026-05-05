"""Engine Runner 实现命名空间。

本包承载 :class:`~dayu.engine.contracts.runner.AsyncRunner` 协议的具体
实现。Phase 1 仅落地 OpenAI 兼容协议的实现位于
:mod:`dayu.engine.runners.openai`。

设计要点：

- 包根**不**导出任何实现类；调用方在 Host 装配阶段直接 ``from
  dayu.engine.runners.openai.runner import AsyncOpenAIRunner`` 显式导入，
  避免污染 :data:`dayu.engine.__all__`。
- 实现包内禁止反向 import :mod:`dayu.host` / :mod:`dayu.service` /
  :mod:`dayu.ui` / :mod:`dayu.fins`，违反由
  :mod:`tests.engine.test_import_boundary` 守护。
"""

from __future__ import annotations

__all__: list[str] = []
