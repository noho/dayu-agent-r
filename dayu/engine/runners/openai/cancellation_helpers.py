"""Runner 内部协作式取消信号。

本模块仅保留 Runner 内部私有异常 :class:`_RunnerInterrupted`。通用的
协作式取消等待 helper 已迁移到 :mod:`dayu.runtime.cancellation`，
Runner 直接 ``import`` 公共 helper 并在边界把
:class:`~dayu.runtime.cancellation.WaitCancelled` 翻译为
:class:`_RunnerInterrupted`，由生成器顶层捕获后**直接退出**生成器。

设计要点：

- :class:`_RunnerInterrupted` 仅在 :mod:`dayu.engine.runners.openai`
  实现内部传递；**不**暴露在公共 ``__all__``，**不**写入任何公共方法的
  ``:raises:`` 文档。
- :class:`_RunnerInterrupted` 不是 :class:`asyncio.CancelledError` 的子类，
  避免被外部 ``except asyncio.CancelledError`` 误吞或导致任务被错误取消。
"""

from __future__ import annotations


class _RunnerInterrupted(Exception):
    """Runner 内部协作式取消信号。

    仅在 :mod:`dayu.engine.runners.openai` 实现内部传递；**不**暴露
    在公共 ``__all__``，**不**写入任何公共方法的 ``:raises:`` 文档。
    """


__all__: list[str] = []
